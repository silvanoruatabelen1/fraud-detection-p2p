"""Reproduce el tráfico real del período de prueba contra la API, hora por hora.

Simula la llegada de operaciones a la billetera: cada step (una hora de PaySim) se envía en un lote
y se espera `--seconds-per-hour` entre horas. Las etiquetas viajan para alimentar los KPI como si
se conocieran después (contracargos o denuncias); el modelo no las usa.

    python -m replayer.replay --api http://localhost:8000 --seconds-per-hour 2
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger("replayer")
ROOT = Path(__file__).resolve().parents[1]


def wait_for_api(api: str, timeout_s: int = 180) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if requests.get(f"{api}/health", timeout=3).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError(f"La API no respondió en {timeout_s} s")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--data", type=Path, default=ROOT / "data" / "demo" / "replay.parquet")
    p.add_argument("--seconds-per-hour", type=float, default=2.0, help="pausa entre horas simuladas")
    p.add_argument("--reset", action="store_true", help="borra el tráfico previo antes de empezar")
    a = p.parse_args(argv)

    wait_for_api(a.api)
    if a.reset:
        requests.delete(f"{a.api}/v1/admin/traffic", timeout=30).raise_for_status()
    df = pd.read_parquet(a.data)
    done = requests.get(f"{a.api}/v1/kpis/summary", timeout=30).json().get("last_step") or 0
    df = df[df["step"] > done]
    log.info("Reproduciendo %s operaciones (%s horas) desde el step %s", f"{len(df):,}", df["step"].nunique(), done + 1)
    for step, g in df.groupby("step", sort=True):
        rows = [
            {
                "step": int(r.step),
                "type": r.type,
                "amount": float(r.amount),
                "old_balance_orig": float(r.oldbalanceOrg),
                "name_dest": r.nameDest,
                "name_orig": r.nameOrig,
                "label": int(r.isFraud),
                "sample_weight": float(r.sample_weight),
            }
            for r in g.itertuples()
        ]
        r = requests.post(f"{a.api}/v1/score/batch", json={"transactions": rows, "source": "replay"}, timeout=120)
        r.raise_for_status()
        out = r.json()
        log.info(
            "Día %d, %02d h: %d operaciones, %d rojas, %d ámbar",
            (step - 1) // 24 + 1,
            step % 24,
            out["processed"],
            out["red"],
            out["amber"],
        )
        time.sleep(a.seconds_per_hour)
    log.info("Reproducción completa")


if __name__ == "__main__":
    main()
