from pathlib import Path

import pandas as pd
import streamlit as st
from core import f_int, f_num, get, guard, setup

FIGS = Path(__file__).resolve().parents[2] / "reports" / "figures"

setup("Modelo y evaluación", "Qué modelo decide, con qué datos se eligió y qué tan confiable es el resultado.")
m = guard(lambda: get("/v1/model"))
t = m["test_metrics"]

rows = []
for key, name in (
    ("rule_isFlaggedFraud", "Regla vigente (isFlaggedFraud)"),
    ("champion", "Campeón: regresión logística"),
    ("champion_upper_edge", "Campeón con el umbral original (borde superior)"),
    ("challenger", "Retador: XGBoost"),
    ("challenger_adv", "XGBoost entrenado con ataques"),
    ("sentinel", "Centinela sin firmas"),
):
    v = t[key]
    rows.append(
        {
            "Estrategia": name,
            "Fraudes detenidos": f"{f_int(v['tp'])} de {f_int(v['tp'] + v['fn'])}",
            "Clientes honestos retenidos": f_int(v["fp"]),
            "Alertas por día": f_num(v["alerts_per_day"], 1),
            "PR-AUC": f_num(v["pr_auc"], 5) if "pr_auc" in v else "—",
            "Ahorro": f"{f_num(v['savings_pct'], 2)}%",
        }
    )
st.subheader("Prueba: días 16 a 31 (505.511 operaciones de riesgo, 4.196 fraudes)")
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
ci = t["champion"]["recall_ci95"]
st.caption(
    f"Sensibilidad del campeón: IC 95% de Wilson {f_num(100 * ci[0], 2)}% a {f_num(100 * ci[1], 2)}%. "
    "Cupo de 1.000 revisiones diarias con cola por orden de llegada."
)

left, right = st.columns(2, gap="large")
with left:
    st.subheader("Cómo se eligió")
    st.markdown(
        "- **Partición cronológica:** entrenamiento días 1 a 12, validación 13 a 15, prueba 16 a 31.\n"
        "- **12 atributos ex ante**, conocidos al autorizar; el historial del destino usa la ventana [t − 168 h, t).\n"
        "- **Seis familias** comparadas con validación cruzada de origen móvil y PR-AUC: quedaron dentro de un error estándar "
        "(0,99783 a 0,99805). Por la regla de un error estándar gana la más simple, la logística.\n"
        "- **Umbral económico:** punto medio de la franja con al menos el 99,9% del ahorro máximo, con el cupo verificado día por día."
    )
    hp = m["hyperparameters"]
    st.markdown(
        f"**Campeón:** regresión logística, C = {hp['champion']['C']}, sin reponderar, escalado estándar. "
        f"**Retador:** XGBoost, profundidad {hp['challenger']['max_depth']}, tasa {hp['challenger']['learning_rate']}, "
        f"{hp['challenger']['n_estimators']} árboles."
    )
with right:
    st.subheader("Límites que conviene saber")
    st.markdown(
        "- **Datos simulados.** Las regularidades más fuertes son reglas del simulador: una regla de dos firmas iguala al modelo.\n"
        "- **Fragilidad ante cambios de táctica.** Si el atacante deja un centavo, el campeón detecta 0,3%. El XGBoost entrenado con "
        "ataques llega a 86,9% ante retiros del 90%, pero cae con retiros chicos que no vio.\n"
        "- **Umbral revisado tras la prueba.** El punto medio se adoptó después de observar la prueba; la cifra conservadora es "
        f"{f_num(t['champion_upper_edge']['savings_pct'], 2)}%.\n"
        "- **Costos supuestos.** El ahorro casi no cambia al multiplicar los costos hasta por 20; sí cambia con el cupo."
    )

for name, caption in (
    ("F10_umbral_economico.png", "Umbral económico en validación"),
    (
        "F15_bateria_escenarios.png",
        "Batería de 18 ataques: fraudes detenidos según la parte del saldo que retira el atacante",
    ),
):
    if (FIGS / name).exists():
        st.image(str(FIGS / name), caption=caption, use_container_width=True)
st.caption("El análisis completo está en `notebooks/` y en `docs/informe_tecnico.pdf`.")
