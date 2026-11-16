import pandas as pd
import streamlit as st
from core import ACCENT, FRAUD, LABELS, OK, api, contributions_chart, f_int, f_money, f_num, get, guard, kpi, setup

setup(
    "Cola de alertas",
    "Lo que ve el equipo de Prevención de Fraude: las operaciones retenidas (rojo) y las que pidieron "
    "verificación (ámbar), con el motivo de cada una.",
)

s = guard(lambda: get("/v1/kpis/summary"))
c = st.columns(4)
kpi(
    c[0],
    "Pendientes en rojo",
    f_int(len(guard(lambda: get("/v1/alerts", tier="rojo", status="pendiente", limit=2000)))),
    "Fondos retenidos",
    FRAUD,
)
kpi(
    c[1],
    "Pendientes en ámbar",
    f_int(len(guard(lambda: get("/v1/alerts", tier="ambar", status="pendiente", limit=2000)))),
    "Verificación automática",
    ACCENT,
)
kpi(
    c[2],
    "Revisadas",
    f_int(len(guard(lambda: get("/v1/alerts", tier="rojo", status="revisada", limit=2000)))),
    "Confirmadas o liberadas",
    OK,
)
kpi(
    c[3],
    "Precisión del rojo",
    "—" if not s.get("precision") else f"{f_num(100 * s['precision'], 1)}%",
    "Según etiquetas confirmadas",
)

st.write("")
tier = st.segmented_control(
    "Nivel", ["rojo", "ambar"], default="rojo", format_func=lambda t: "Rojo" if t == "rojo" else "Ámbar"
)
status = st.segmented_control(
    "Estado", ["pendiente", "revisada", "todas"], default="pendiente", format_func=str.capitalize
)
rows = guard(lambda: get("/v1/alerts", tier=tier or "rojo", status=status or "pendiente", limit=500))
if not rows:
    st.info(
        "No hay alertas con ese filtro."
        + (
            " El nivel ámbar es poco frecuente: en la prueba completa fueron 9 por día, todas de clientes honestos."
            if tier == "ambar"
            else ""
        )
    )
    st.stop()

df = pd.DataFrame(rows)
view = pd.DataFrame(
    {
        "ID": df["tx_id"],
        "Día": df["day"],
        "Hora": df["hour"].map(lambda h: f"{h:02d} h"),
        "Tipo": df["type"],
        "Monto": df["amount"].map(f_money),
        "Saldo de origen": df["old_balance_orig"].map(f_money),
        "Probabilidad": df["probability"].map(lambda p: f"{f_num(100 * p, 2)}%"),
        "Motivo principal": df["reasons"].str.split(" · ").str[0],
        "Estado": df["status"].fillna("pendiente").str.replace("_", " "),
    }
)
st.caption("Seleccioná una fila para ver el detalle y resolverla.")
sel = st.dataframe(
    view, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", height=330
)
picked = sel.selection.rows
if picked:
    r = df.iloc[picked[0]]
    st.divider()
    left, right = st.columns([5, 7], gap="large")
    with left:
        st.markdown(f"#### Operación {r['tx_id']}")
        st.markdown(
            f"**{r['type']}** de {f_money(r['amount'])} desde una cuenta con {f_money(r['old_balance_orig'])} de saldo, "
            f"día {r['day']} a las {r['hour']:02d} h, hacia `{r['name_dest']}` "
            f"({f_int(r['dest_ops_prev'])} operaciones recibidas en las 168 h previas)."
        )
        st.markdown(f"**Motivos:** {r['reasons']}")
        a, b = st.columns(2)
        if a.button("Confirmar fraude", type="primary", use_container_width=True):
            api("POST", f"/v1/alerts/{r['tx_id']}/review", json={"status": "fraude_confirmado"})
            st.cache_data.clear()
            st.rerun()
        if b.button("Liberar operación", use_container_width=True):
            api("POST", f"/v1/alerts/{r['tx_id']}/review", json={"status": "liberado"})
            st.cache_data.clear()
            st.rerun()
    with right:
        if isinstance(r["contributions"], dict):
            st.plotly_chart(contributions_chart(r["contributions"], LABELS, height=320), use_container_width=True)
