import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core import ACCENT, FRAUD, LEGIT, OK, demo_notice, f_int, f_pct, get, guard, kpi, setup

setup(
    "Experiencia del cliente",
    "Para Marketing y Atención: cuántos clientes honestos sienten el sistema y si la fricción "
    "se reparte de forma pareja entre segmentos.",
)

s = guard(lambda: get("/v1/kpis/summary"))
seg = guard(lambda: get("/v1/kpis/segments"))
if not seg:
    st.info("Todavía no hay tráfico procesado.")
    st.stop()
df = pd.DataFrame(seg)
legit = df[df["dimension"] == "type"]["legit_operations"].sum()
amber = df[df["dimension"] == "type"]["amber_legit"].sum()
red = df[df["dimension"] == "type"]["red_legit"].sum()

c = st.columns(4)
kpi(c[0], "Operaciones aprobadas sin fricción", f_pct(s["green_pct"], 2), "Sobre todo el tráfico", OK)
kpi(c[1], "Clientes honestos retenidos", f_int(red), "Fondos frenados sin motivo", FRAUD)
kpi(c[2], "Clientes honestos con verificación", f_int(amber), "Paso extra: código o huella", ACCENT)
kpi(
    c[3],
    "Tasa de fricción en legítimas",
    f_pct(100 * (amber + red) / legit if legit else None, 3),
    f"{f_int(legit)} operaciones legítimas",
)

names = {"franja": "Franja horaria", "historial": "Historial de la cuenta de destino", "type": "Tipo de operación"}
st.subheader("Fricción sobre clientes honestos por segmento")
st.caption(
    "Porcentaje de operaciones legítimas que recibirían una retención o una verificación. El campeón es el que decide hoy; "
    "los modelos de control corren en sombra y muestran cuánta fricción costaría usarlos para decidir."
)
cols = st.columns(3)
for col, (dim, title) in zip(cols, names.items(), strict=True):
    d = df[df["dimension"] == dim]
    fig = go.Figure()
    fig.add_bar(
        x=d["segment"],
        y=d["friction_rate_pct"],
        name="Campeón (decide)",
        marker_color=LEGIT,
        text=[f_pct(v, 2) for v in d["friction_rate_pct"]],
        textposition="outside",
    )
    fig.add_bar(
        x=d["segment"],
        y=d["control_rate_pct"],
        name="Modelos de control",
        marker_color=ACCENT,
        text=[f_pct(v, 2) for v in d["control_rate_pct"]],
        textposition="outside",
    )
    fig.update_layout(
        height=320,
        title=title,
        barmode="group",
        yaxis=dict(rangemode="tozero", title="% de legítimas"),
        uniformtext_minsize=9,
    )
    col.plotly_chart(fig, use_container_width=True)

st.markdown(
    "**Cómo leerlo.** En la prueba completa el campeón no retuvo a ningún cliente honesto en ningún segmento. Con cero "
    "eventos, la tasa real hacia destinos sin historial queda acotada en 28,3 por millón de legítimas (intervalo de Wilson al "
    "95%). La fricción de los modelos de control se concentra en la madrugada y en los destinos nuevos: por eso no deciden, "
    "y sus alertas se leen por franja horaria."
)
demo_notice()
