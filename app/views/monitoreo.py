import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core import ACCENT, FRAUD, LEGIT, NEUTRAL, OK, f_int, f_money, f_num, get, guard, kpi, setup

setup(
    "Monitoreo y deriva",
    "El modelo depende de una firma exacta del atacante. Esta página vigila dos cosas: que los datos "
    "sigan pareciéndose a los de entrenamiento y que los modelos de control no empiecen a ver fraudes que el campeón deja pasar.",
)

drift = pd.DataFrame(guard(lambda: get("/v1/monitoring/drift")))
shadow = guard(lambda: get("/v1/monitoring/shadow"))
if drift.empty:
    st.info("Todavía no hay tráfico procesado.")
    st.stop()

daily = pd.DataFrame(shadow["daily"])
confirmed = daily["tactic_signals_confirmed_fraud"].sum() if len(daily) else 0
score_psi = drift.loc[drift["variable"] == "__score__", "psi"].iloc[0]
c = st.columns(3)
worst = drift[drift["variable"] != "__score__"].sort_values("psi").iloc[-1]
kpi(
    c[0], "PSI del puntaje", f_num(score_psi, 3), "< 0,10 estable · > 0,25 relevante", OK if score_psi < 0.1 else ACCENT
)
kpi(c[1], "Atributo con más deriva", worst["variable"], f"PSI {f_num(worst['psi'], 3)} · {worst['estado']}", NEUTRAL)
kpi(
    c[2],
    "Señales de cambio de táctica confirmadas",
    f_int(confirmed),
    "Fraudes que el campeón aprobó y un control marcó",
    FRAUD,
)

d = drift.sort_values("psi")
colors = [OK if v < 0.1 else ACCENT if v < 0.25 else FRAUD for v in d["psi"]]
fig = go.Figure(
    go.Bar(
        x=d["psi"], y=d["variable"].replace({"__score__": "PUNTAJE DEL CAMPEÓN"}), orientation="h", marker_color=colors
    )
)
fig.add_vline(x=0.10, line_dash="dot", line_color=ACCENT)
fig.add_vline(x=0.25, line_dash="dot", line_color=FRAUD)
fig.update_layout(
    height=380, title="Índice de estabilidad poblacional frente a entrenamiento (últimas 72 h, ponderado)"
)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "La deriva esperada está en el historial del destino: en la segunda quincena cae el volumen legítimo y menos cuentas "
    "tienen actividad previa. Un PSI alto en los atributos monto-saldo, en cambio, sería una alarma de cambio de táctica."
)

if len(daily):
    fig = go.Figure()
    for k, name, color in (
        ("champion", "Campeón (decide)", LEGIT),
        ("challenger", "Retador XGBoost", NEUTRAL),
        ("challenger_adv", "XGBoost entrenado con ataques", ACCENT),
        ("sentinel", "Centinela sin firmas", FRAUD),
    ):
        fig.add_scatter(x=daily["day"], y=daily[k], mode="lines+markers", name=name, line=dict(color=color))
    fig.update_layout(
        height=320,
        title="Alertas por día de cada modelo (los de control no retienen a nadie)",
        xaxis=dict(dtick=1, title="Día"),
    )
    st.plotly_chart(fig, use_container_width=True)
st.markdown(
    "**Cómo leerlo.** Los modelos de control alertan más que el campeón porque generalizan a retiros parciales a costa de "
    "marcar operaciones legítimas, sobre todo de madrugada. Sus alertas no se ejecutan: se comparan con las etiquetas que llegan "
    "después. Mientras las señales confirmadas sean cero, el atacante sigue vaciando cuentas; si empiezan a crecer, cambió de "
    "táctica y corresponde reentrenar con los casos nuevos."
)
recent = pd.DataFrame(shadow["recent_signals"])
if len(recent):
    with st.expander("Últimas señales de los modelos de control"):
        st.dataframe(
            recent.assign(
                amount=recent["amount"].map(f_money), score=recent["score"].map(lambda v: f_num(v, 2))
            ).rename(
                columns={
                    "id": "ID",
                    "step": "Step",
                    "type": "Tipo",
                    "amount": "Monto",
                    "score": "Puntaje campeón",
                    "challenger_adv_alert": "XGBoost con ataques",
                    "sentinel_alert": "Centinela",
                    "fraud": "Fraude confirmado",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
