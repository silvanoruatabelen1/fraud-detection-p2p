import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core import ACCENT, FRAUD, LEGIT, NEUTRAL, OK, demo_notice, f_int, f_money, f_num, f_pct, get, guard, kpi, setup

setup("Riesgo y finanzas", "Cuánto dinero protege el sistema, cuánto cuesta operarlo y qué pasa si cambian los supuestos.")

s = guard(lambda: get("/v1/kpis/summary"))
if s.get("operations"):
    c = st.columns(4)
    kpi(c[0], "Monto defraudado intentado", f_money(s["fraud_amount"]), f"{f_int(s['frauds'])} fraudes", FRAUD)
    kpi(c[1], "Monto protegido", f_money(s["protected_amount"]), f"{f_pct(100 * s['protected_amount'] / s['fraud_amount'], 2)} del intentado", OK)
    kpi(c[2], "Costo de operación", f_money(s["review_cost"] + s["friction_cost"]),
        f"Revisión {f_money(s['review_cost'])} · fricción {f_money(s['friction_cost'])}", NEUTRAL)
    kpi(c[3], "Ahorro neto", f_money(s["net_savings"]), f"{f_pct(s['savings_pct'], 2)} del monto defraudado", LEGIT)

    daily = pd.DataFrame(guard(lambda: get("/v1/kpis/daily")))
    fig = go.Figure()
    fig.add_bar(x=daily["day"], y=daily["protected_amount"] / 1e6, name="Protegido", marker_color=OK)
    fig.add_bar(x=daily["day"], y=(daily["fraud_amount"] - daily["protected_amount"]) / 1e6, name="Perdido", marker_color=FRAUD)
    fig.update_layout(barmode="stack", height=320, title="Monto defraudado intentado por día: protegido y perdido (millones de u.m.)",
                      xaxis=dict(title="Día", dtick=1))
    st.plotly_chart(fig, use_container_width=True)
    demo_notice()

st.divider()
st.subheader("Simulador de escenarios económicos")
st.markdown("Los costos y el cupo del equipo son supuestos. Al cambiarlos, el umbral se vuelve a elegir en **validación** "
            "(días 13 a 15) y se aplica a la **prueba completa** (días 16 a 31, 4.196 fraudes), con una cola diaria que atiende "
            "las alertas por orden de llegada hasta completar el cupo.")
a, b, c = st.columns(3)
review = a.number_input("Costo por alerta revisada (u.m.)", 0, 100_000, 1_500, 500)
friction = b.number_input("Fricción por cliente honesto retenido (u.m.)", 0, 1_000_000, 8_500, 500)
cap = c.select_slider("Cupo de revisiones por día", [25, 50, 100, 200, 300, 500, 1000, 2000, 5000], value=1000)
w = guard(lambda: get("/v1/economics/whatif", review_cost=review, friction_cost=friction, daily_capacity=cap))
t = w["test"]
c = st.columns(4)
kpi(c[0], "Ahorro en prueba", f_pct(t["savings_pct"], 2), f"{f_money(t['savings'])}", LEGIT)
kpi(c[1], "Fraudes detenidos", f"{f_int(t['tp'])} de {f_int(t['tp'] + t['fn'])}", f"Sensibilidad {f_pct(100 * t['recall'], 2)}", OK)
kpi(c[2], "Clientes honestos retenidos", f_int(t["fp"]), f"Precisión {f_pct(100 * t['precision'], 2)}", FRAUD)
kpi(c[3], "Alertas atendidas", f"{f_int(t['alerts'])} de {f_int(t['candidates'])}",
    f"{f_num(t['alerts_per_day'], 1)} por día · umbral {f_num(w['threshold'], 2)}", ACCENT)
if t["candidates"] > t["alerts"]:
    st.warning(f"El cupo no alcanza: {f_int(t['candidates'] - t['alerts'])} alertas quedaron sin atender. Con este equipo el problema "
               "no es el modelo sino la capacidad de revisión.")

curve = pd.DataFrame(w["curve"])
fig = go.Figure()
fig.add_scatter(x=curve["threshold"], y=curve["savings"] / 1e6, mode="lines", line=dict(color=LEGIT), name="Ahorro en validación")
inf = curve[~curve["feasible"]]
fig.add_scatter(x=inf["threshold"], y=inf["savings"] / 1e6, mode="markers", marker=dict(color=FRAUD, size=4), name="Supera el cupo")
fig.add_vrect(x0=w["band"][0], x1=w["band"][1], fillcolor=OK, opacity=0.08, line_width=0)
fig.add_vline(x=w["threshold"], line_color=ACCENT, line_dash="dash", annotation_text="umbral elegido")
top = curve["savings"].max() / 1e6
fig.update_layout(height=330, title="Ahorro neto en validación según el umbral (millones de u.m.)",
                  xaxis=dict(title="Umbral (puntaje en log-odds)", range=[-13, 12]), yaxis=dict(range=[0, top * 1.12]))
st.plotly_chart(fig, use_container_width=True)
st.caption("Franja verde: umbrales factibles con al menos el 99,9% del ahorro máximo. Se elige su punto medio, porque los bordes "
           "quedan fijados por una sola operación de validación.")
