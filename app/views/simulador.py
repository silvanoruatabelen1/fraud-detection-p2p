import time

import streamlit as st
from core import FRAUD, LABELS, LEGIT, TIER_COLOR, api, contributions_chart, f_int, f_money, f_num, get, guard, setup

TYPES = {"TRANSFER": "Transferencia a otra cuenta", "CASH_OUT": "Retiro en efectivo", "PAYMENT": "Pago a comercio",
         "CASH_IN": "Depósito en efectivo", "DEBIT": "Débito a cuenta bancaria"}
PRESETS = {
    "Vacía la cuenta": dict(type="TRANSFER", amount=181_000.0, balance=181_000.0, day=17, hour=3),
    "Retira el 90%": dict(type="TRANSFER", amount=162_900.0, balance=181_000.0, day=17, hour=3),
    "Retiro habitual": dict(type="CASH_OUT", amount=45_000.0, balance=12_500.0, day=17, hour=14),
    "Tramo de 10 M": dict(type="TRANSFER", amount=10_000_000.0, balance=25_000_000.0, day=17, hour=11),
    "Pago a comercio": dict(type="PAYMENT", amount=3_200.0, balance=50_000.0, day=17, hour=19),
}

setup("Simulador de operaciones", "Cargá una operación y mirá qué decidiría el sistema en el momento de autorizarla, y por qué.")

if "sim" not in st.session_state:
    st.session_state.sim = PRESETS["Vacía la cuenta"]

st.markdown("**Casos de ejemplo**")
cols = st.columns(len(PRESETS))
for col, (name, p) in zip(cols, PRESETS.items(), strict=True):
    if col.button(name, use_container_width=True):
        st.session_state.sim = p

p = st.session_state.sim
left, right = st.columns([5, 7], gap="large")
with left, st.form("tx"):
    tx_type = st.selectbox("Tipo de operación", list(TYPES), index=list(TYPES).index(p["type"]), format_func=lambda t: f"{TYPES[t]} ({t})")
    a, b = st.columns(2)
    amount = a.number_input("Monto (u.m.)", min_value=0.0, value=float(p["amount"]), step=1000.0, format="%.2f")
    balance = b.number_input("Saldo de la cuenta de origen", min_value=0.0, value=float(p["balance"]), step=1000.0, format="%.2f")
    a, b = st.columns(2)
    day = a.slider("Día de la simulación", 16, 31, int(p["day"]))
    hour = b.slider("Hora", 0, 23, int(p["hour"]))
    # En PaySim el step 1 es la 1 h del día 1 y el step 24 es la hora 0 que cierra ese día
    step = (day - 1) * 24 + hour if hour > 0 else day * 24
    examples = guard(lambda: get("/v1/destinations/examples", step=step, limit=6))
    options = ["Cuenta nueva, sin historial"] + [f"{e['name_dest']} · {e['ops']} operaciones recibidas" for e in examples]
    dest_choice = st.selectbox("Cuenta de destino", options, help="El historial de 168 h se calcula desde la base de datos.")
    submitted = st.form_submit_button("Analizar operación", type="primary", use_container_width=True)

with right:
    if not submitted:
        st.markdown("#### Resultado")
        st.caption("El veredicto aparece acá después de analizar la operación.")
    else:
        dest = f"C9{step:04d}{int(amount) % 100000:05d}" if dest_choice.startswith("Cuenta nueva") else dest_choice.split(" · ")[0]
        body = {"step": step, "type": tx_type, "amount": amount, "old_balance_orig": balance, "name_dest": dest, "name_orig": "C_SIMULADOR"}
        with st.spinner("Analizando la operación…"):
            time.sleep(0.6)
            d = guard(lambda: api("POST", "/v1/score", json=body, params={"persist": False}))
        color = TIER_COLOR[d["tier"]]
        verdict = {"rojo": "Posible fraude", "ambar": "Requiere verificación", "verde": "Operación aprobada"}[d["tier"]]
        prob = "" if d["probability"] is None else f" · probabilidad estimada de fraude {f_num(100 * d['probability'], 2)}%"
        st.markdown(f'<div class="fd-verdict" style="background:{color}"><div class="t">{verdict}</div>'
                    f'<div class="a">{d["action"]}{prob}</div></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown("**Por qué**")
        for r in d["reasons"]:
            st.markdown(f"- {r}")
        st.caption(f"Historial del destino en las 168 h previas: {f_int(d['dest_ops_prev'])} operaciones por "
                   f"{f_money(d['dest_amount_prev'])} · tiempo de decisión {f_num(d['latency_ms'], 1)} ms")
        if d["in_scope"]:
            st.plotly_chart(contributions_chart(d["contributions"], LABELS, height=330), use_container_width=True)
            names = {"challenger": "Retador XGBoost", "challenger_adv": "XGBoost entrenado con ataques", "sentinel": "Centinela sin firmas"}
            sc = st.columns(3)
            for col, (k, v) in zip(sc, d["shadow"].items(), strict=True):
                col.markdown(f"<div class='fd-kpi'><div class='lbl'>{names[k]}</div><div class='val' style='font-size:1.1rem;color:"
                             f"{FRAUD if v['alert'] else LEGIT}'>{'Alertaría' if v['alert'] else 'No alertaría'}</div>"
                             f"<div class='sub'>puntaje {f_num(v['score'], 2)}</div></div>", unsafe_allow_html=True)
            if d["tactic_change_signal"]:
                st.warning("El campeón no alertó, pero un modelo de control sí. Si se confirma como fraude, es la señal de que el "
                           "atacante cambió de táctica y corresponde reentrenar.")
            st.caption("Los modelos en sombra no cambian la decisión: vigilan cambios de comportamiento del atacante.")
