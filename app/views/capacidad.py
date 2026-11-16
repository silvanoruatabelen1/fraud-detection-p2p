import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core import ACCENT, FRAUD, LEGIT, demo_notice, f_int, f_num, get, guard, kpi, setup

setup(
    "Capacidad del equipo",
    "Para Recursos Humanos y la jefatura de Prevención: cuántas alertas llegan, cuándo, y cuántos "
    "analistas hacen falta para atenderlas sin superar el cupo.",
)

h = guard(lambda: get("/v1/kpis/hourly"))
if not h["rows"]:
    st.info("Todavía no hay tráfico procesado.")
    st.stop()
df = pd.DataFrame(h["rows"])
cap = h["capacity_per_day"]
daily = df.groupby("day")[["red", "amber", "operations"]].sum().reset_index()

a, b = st.columns(2)
cases = a.number_input("Casos que resuelve un analista por turno", 10, 200, 60, 5)
shifts = b.number_input("Turnos por día", 1, 3, 3)
peak_day = daily["red"].max()
analysts = math.ceil(peak_day / (cases * shifts)) if peak_day else 0

c = st.columns(4)
kpi(c[0], "Alertas rojas por día", f_num(daily["red"].mean(), 1), f"Máximo {f_int(peak_day)}", FRAUD)
kpi(c[1], "Verificaciones ámbar por día", f_num(daily["amber"].mean(), 1), "Automáticas, sin analista", ACCENT)
kpi(
    c[2],
    "Uso del cupo en el día pico",
    f"{f_num(100 * peak_day / cap, 1)}%",
    f"Cupo supuesto: {f_int(cap)} por día",
    LEGIT,
)
kpi(c[3], "Analistas necesarios", f_int(analysts), f"Por turno, con {cases} casos cada uno")

fig = go.Figure()
fig.add_bar(x=daily["day"], y=daily["red"], name="Rojas", marker_color=FRAUD)
fig.add_bar(x=daily["day"], y=daily["amber"], name="Ámbar", marker_color=ACCENT)
fig.add_hline(y=cap, line_dash="dash", line_color="#667085", annotation_text=f"cupo {f_int(cap)}")
fig.update_layout(
    barmode="stack", height=300, title="Alertas por día frente al cupo de revisión", xaxis=dict(title="Día", dtick=1)
)
st.plotly_chart(fig, use_container_width=True)

pivot = df.pivot_table(index="day", columns="hour", values="red", aggfunc="sum").fillna(0)
heat = go.Figure(
    go.Heatmap(
        z=pivot.values,
        x=[f"{c:02d}" for c in pivot.columns],
        y=[f"Día {d}" for d in pivot.index],
        colorscale=[[0, "#FFFFFF"], [1, FRAUD]],
        hovertemplate="%{y}, %{x} h: %{z:.0f} alertas<extra></extra>",
    )
)
heat.update_layout(height=260, title="Alertas rojas por hora: cuándo se concentra la carga", xaxis_title="Hora")
st.plotly_chart(heat, use_container_width=True)
st.caption(
    "El fraude de PaySim es estable a lo largo del día; lo que cae de madrugada es el volumen legítimo. Por eso la carga "
    "de alertas no sigue el ritmo del tráfico y conviene cubrir también los turnos nocturnos."
)
demo_notice()
