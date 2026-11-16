"""Pipeline reproducible: CSV -> bronce -> plata -> oro -> modelos, umbrales, métricas y datos de demo.

Uso:
    python -m fraud_p2p.pipeline all --csv data/raw/p2p.csv
    python -m fraud_p2p.pipeline train      # requiere la capa oro
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

from . import __version__
from .adversarial import augment_partial_withdrawals
from .constants import FEATURES, SENTINEL_FEATURES, TRAIN_END_STEP, VALID_END_STEP, day_of_step
from .data import curate, read_raw_csv, write_parquet
from .economics import CostConfig, evaluate_alerts, optimal_threshold, serve_daily_queue, wilson_interval
from .features import build_gold
from .models import CHALLENGER_PARAMS, CHAMPION_PARAMS, SEED, make_challenger, make_champion, score, sigmoid
from .monitoring import build_reference

log = logging.getLogger("fraud_p2p.pipeline")

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"
BRONZE = DATA / "bronze" / "paysim.parquet"
SILVER = DATA / "silver" / "paysim_curada.parquet"
GOLD = DATA / "gold" / "atributos_riesgo.parquet"


def ingest(csv: Path) -> None:
    raw = read_raw_csv(csv)
    write_parquet(raw, BRONZE)
    write_parquet(curate(raw), SILVER)


def features() -> None:
    t0 = time.perf_counter()
    gold = build_gold(pd.read_parquet(SILVER))
    write_parquet(gold, GOLD)
    log.info("Capa oro: %s operaciones de riesgo en %.1f s", f"{len(gold):,}", time.perf_counter() - t0)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def train(costs: CostConfig = CostConfig()) -> dict:
    gold = pd.read_parquet(GOLD)
    step = gold["step"].to_numpy()
    days = day_of_step(step)
    y = gold["isFraud"].to_numpy().astype(np.int8)
    amount = gold["amount"].to_numpy()
    tr, va, te = step <= TRAIN_END_STEP, (step > TRAIN_END_STEP) & (step <= VALID_END_STEP), step > VALID_END_STEP
    X = gold[FEATURES]
    n_days = {"validation": 3, "test": 16}

    log.info("Entrenando campeón, retador y centinela con los días 1 a 12")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        models = {
            "champion": make_champion().fit(X[tr], y[tr]),
            "challenger": make_challenger().fit(X[tr], y[tr]),
            "sentinel": make_champion().fit(gold.loc[tr, SENTINEL_FEATURES], y[tr]),
        }
        # Retador entrenado con ataques sintéticos: 4 copias por fraude en entrenamiento, 2 en validación
        rng = np.random.default_rng(SEED)
        Xa_tr, _, _ = augment_partial_withdrawals(gold, tr, 4, rng)
        Xa_va, ma_va, sa_va = augment_partial_withdrawals(gold, va, 2, rng)
        X_tr_aug = pd.concat([X[tr].reset_index(drop=True), Xa_tr[FEATURES]], ignore_index=True)
        y_tr_aug = np.r_[y[tr], np.ones(len(Xa_tr), dtype=np.int8)]
        models["challenger_adv"] = make_challenger().fit(X_tr_aug, y_tr_aug)

    cols = {"champion": FEATURES, "challenger": FEATURES, "sentinel": SENTINEL_FEATURES, "challenger_adv": FEATURES}
    scores = {k: {split: score(m, gold.loc[mask, cols[k]]) for split, mask in (("tr", tr), ("va", va), ("te", te))}
              for k, m in models.items()}

    thresholds, bands = {}, {}
    for k in ("champion", "challenger", "sentinel"):
        o = optimal_threshold(y[va], scores[k]["va"], amount[va], days[va], costs)
        thresholds[k], bands[k] = o["threshold"], (o["band_min"], o["band_max"])
    # En la validación aumentada el cupo se verifica solo sobre las operaciones reales
    X_va_aug = pd.concat([X[va].reset_index(drop=True), Xa_va[FEATURES]], ignore_index=True)
    s_va_aug = score(models["challenger_adv"], X_va_aug)
    o = optimal_threshold(np.r_[y[va], np.ones(len(Xa_va), dtype=np.int8)], s_va_aug, np.r_[amount[va], ma_va],
                          np.r_[days[va], day_of_step(sa_va)], costs, counts=np.r_[np.ones(va.sum(), bool), np.zeros(len(Xa_va), bool)])
    thresholds["challenger_adv"], bands["challenger_adv"] = o["threshold"], (o["band_min"], o["band_max"])

    # Evaluación en prueba (días 16 a 31) con cola diaria de atención
    metrics: dict = {"test": {}, "validation": {}}
    fraud_te = float(amount[te][y[te] == 1].sum())
    for k in models:
        cand = scores[k]["te"] >= thresholds[k]
        served = serve_daily_queue(cand, days[te], costs.daily_capacity)
        e = evaluate_alerts(y[te], served, amount[te], n_days["test"], costs)
        lo, hi = wilson_interval(e["tp"], int(y[te].sum()))
        metrics["test"][k] = {**e, "pr_auc": float(average_precision_score(y[te], scores[k]["te"])),
                              "savings_pct": 100 * e["savings"] / fraud_te, "recall_ci95": [lo, hi],
                              "candidates": int(cand.sum())}
        metrics["validation"][k] = {"pr_auc": float(average_precision_score(y[va], scores[k]["va"])),
                                    "threshold": thresholds[k], "band": list(bands[k])}
    rule = gold["isFlaggedFraud"].to_numpy()[te] == 1
    metrics["test"]["rule_isFlaggedFraud"] = {**evaluate_alerts(y[te], rule, amount[te], n_days["test"], costs)}
    metrics["test"]["rule_isFlaggedFraud"]["savings_pct"] = 100 * metrics["test"]["rule_isFlaggedFraud"]["savings"] / fraud_te
    upper = scores["champion"]["te"] >= bands["champion"][1]
    e_up = evaluate_alerts(y[te], serve_daily_queue(upper, days[te], costs.daily_capacity), amount[te], 16, costs)
    metrics["test"]["champion_upper_edge"] = {**e_up, "savings_pct": 100 * e_up["savings"] / fraud_te}
    metrics["test"]["brier_champion"] = float(brier_score_loss(y[te], sigmoid(scores["champion"]["te"])))

    ARTIFACTS.joinpath("models").mkdir(parents=True, exist_ok=True)
    files = {}
    for k, m in models.items():
        path = ARTIFACTS / "models" / f"{k}.joblib"
        joblib.dump(m, path, compress=3)
        files[k] = {"file": path.name, "sha256_12": _sha(path)}

    reference = build_reference(gold.loc[tr, FEATURES], scores["champion"]["tr"])
    metadata = {
        "package_version": __version__,
        "model_version": f"{__version__}+{files['champion']['sha256_12']}",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "features": FEATURES,
        "sentinel_features": SENTINEL_FEATURES,
        "partition": {"train": "steps 1-288 (días 1-12)", "validation": "steps 289-360 (días 13-15)",
                      "test": "steps 361-743 (días 16-31)"},
        "hyperparameters": {"champion": CHAMPION_PARAMS, "challenger": CHALLENGER_PARAMS},
        "costs": costs.__dict__,
        "thresholds": {
            "red": thresholds["champion"],
            "amber": bands["champion"][0],
            "upper_edge": bands["champion"][1],
            "challenger": thresholds["challenger"],
            "sentinel": thresholds["sentinel"],
            "challenger_adv": thresholds["challenger_adv"],
            "criterion": "punto medio de la franja factible con al menos el 99,9% del ahorro máximo de validación; "
                         "cupo verificado día por día",
            "scale": "log-odds",
        },
        "artifacts": files,
        "reference": reference,
    }
    (ARTIFACTS / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=float))

    # Puntajes de validación y prueba para el simulador de escenarios económicos de la aplicación
    ARTIFACTS.joinpath("eval").mkdir(parents=True, exist_ok=True)
    for split, mask in (("validation", va), ("test", te)):
        pd.DataFrame({"step": step[mask].astype(np.int16), "amount": amount[mask], "y": y[mask],
                      "score": scores["champion"]["va" if split == "validation" else "te"].astype(np.float32)}
                     ).to_parquet(ARTIFACTS / "eval" / f"{split}_scores.parquet", index=False, compression="zstd")

    m = metrics["test"]["champion"]
    log.info("Prueba: %d de %d fraudes, %d falsos positivos, ahorro %.2f%%, PR-AUC %.5f",
             m["tp"], m["tp"] + m["fn"], m["fp"], m["savings_pct"], m["pr_auc"])
    return metrics


def demo_data(days: tuple[int, int] = (16, 18), legit_fraction: float = 0.05) -> None:
    """Conjunto de demostración: tráfico real de prueba y el historial exacto que necesita.

    - replay: todos los fraudes del subespacio de riesgo en `days` y una muestra de las legítimas
      (con su peso de muestreo para reponderar los KPI a volúmenes reales).
    - history_seed: las demás operaciones hacia esos destinos desde 168 h antes, para que el
      historial que calcula la API coincida exactamente con el del entrenamiento.
    """
    cols = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "nameDest", "isFraud"]
    df = pd.read_parquet(SILVER, columns=cols)
    df["type"] = df["type"].astype(str)
    day = day_of_step(df["step"])
    window = df[(day >= days[0]) & (day <= days[1]) & df["type"].isin(["TRANSFER", "CASH_OUT"])]
    legit = window[window["isFraud"] == 0].sample(frac=legit_fraction, random_state=SEED)
    replay = pd.concat([window[window["isFraud"] == 1], legit]).sort_index()
    replay = replay.assign(sample_weight=np.where(replay["isFraud"] == 1, 1.0, 1.0 / legit_fraction))
    smin, smax = int(replay["step"].min()), int(replay["step"].max())
    seed = df[(df["step"] >= smin - 168) & (df["step"] <= smax) & df["nameDest"].isin(replay["nameDest"].unique())
              & ~df.index.isin(replay.index)]
    # Puntaje esperado del campeón calculado fuera de línea: la prueba de paridad exige que la API lo reproduzca
    gold = pd.read_parquet(GOLD)
    gold = gold[gold["step"].between(smin, smax)]
    champion = joblib.load(ARTIFACTS / "models" / "champion.joblib")
    gold = gold.assign(expected_score=score(champion, gold[FEATURES]))
    replay = replay.merge(gold[["step", "nameOrig", "nameDest", "amount", "expected_score"]],
                          on=["step", "nameOrig", "nameDest", "amount"], how="left", validate="one_to_one")
    replay["expected_score"] = replay["expected_score"].where(replay["type"].isin(["TRANSFER", "CASH_OUT"]))
    out = DATA / "demo"
    write_parquet(replay.reset_index(drop=True), out / "replay.parquet")
    write_parquet(seed[["step", "type", "amount", "nameOrig", "oldbalanceOrg", "nameDest"]].reset_index(drop=True),
                  out / "history_seed.parquet")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stage", choices=["ingest", "features", "train", "demo", "all"])
    p.add_argument("--csv", type=Path, default=DATA / "raw" / "p2p.csv")
    a = p.parse_args(argv)
    if a.stage in ("ingest", "all"):
        ingest(a.csv)
    if a.stage in ("features", "all"):
        features()
    if a.stage in ("train", "all"):
        train()
    if a.stage in ("demo", "all"):
        demo_data()


if __name__ == "__main__":
    main()
