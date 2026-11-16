import streamlit as st
from core import FRAUD, LEGIT, OK, demo_notice, f_int, f_money, f_pct, get, guard, kpi, setup

setup(
    "Antifraude P2P · PagoDirecto",
    "Cada transferencia se puntúa en el momento de autorizarla y el puntaje se convierte en una acción "
    "con criterio económico: aprobar, pedir una verificación o retener los fondos para un analista.",
)

health = guard(lambda: get("/health"))
s = guard(lambda: get("/v1/kpis/summary"))
model = guard(lambda: get("/v1/model"))

c = st.columns(4)
if s.get("operations"):
    kpi(c[0], "Ahorro neto", f_money(s["net_savings"]), f"{f_pct(s['savings_pct'])} del monto defraudado", OK)
    kpi(
        c[1],
        "Fraudes detenidos",
        f"{f_int(s['detected'])} de {f_int(s['frauds'])}",
        f"Sensibilidad {f_pct(100 * s['recall'], 2)}",
        FRAUD,
    )
    kpi(c[2], "Clientes honestos retenidos", f_int(s["false_positives"]), "Falsos positivos en rojo", LEGIT)
    kpi(c[3], "Operaciones sin fricción", f_pct(s["green_pct"], 2), f"{f_int(s['operations'])} operaciones estimadas")
    last = s["last_step"]
    st.caption(
        f"Tráfico procesado hasta el día {(last - 1) // 24 + 1}, {last % 24:02d} h · modelo {health['model_version']}"
    )
else:
    st.warning(
        "Todavía no hay tráfico procesado. El servicio `replayer` lo envía al levantar el sistema; también podés "
        "correr `make replay` o probar operaciones sueltas en el **Simulador**."
    )

demo_notice()

st.subheader("Cómo funciona")
st.graphviz_chart(
    """
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#F5F7FA", color="#D0D5DD", fontname="Helvetica", fontsize=11];
  edge [color="#98A2B3", fontname="Helvetica", fontsize=9];
  tx [label="Operación\\n(monto, saldo, tipo,\\nhora, destino)", fillcolor="#FFFFFF"];
  hist [label="Historial del destino\\n[t − 168 h, t)\\nPostgres"];
  feat [label="12 atributos ex ante\\n(misma función que\\nel entrenamiento)"];
  champ [label="Campeón\\nregresión logística", fillcolor="#E8EEF6"];
  thr [label="Umbral económico\\ncon cupo diario"];
  red [label="Rojo: retener\\ny derivar a analista", fillcolor="#FDECEA"];
  amb [label="Ámbar: verificación\\nautomática", fillcolor="#FEF3E2"];
  grn [label="Verde: aprobar", fillcolor="#E6F4F1"];
  shadow [label="En sombra: retador XGBoost,\\nXGBoost entrenado con ataques\\ny centinela sin firmas", style="rounded,dashed"];
  mon [label="Monitoreo: deriva (PSI)\\ny señales de cambio\\nde táctica"];
  tx -> feat; hist -> feat; feat -> champ -> thr; thr -> red; thr -> amb; thr -> grn;
  feat -> shadow -> mon;
}
""",
    use_container_width=True,
)

t = model["test_metrics"]["champion"]
st.subheader("Resultado del modelo en el período de prueba (días 16 a 31)")
st.markdown(
    f"Con el umbral elegido en validación, el campeón detiene **{f_int(t['tp'])} de {f_int(t['tp'] + t['fn'])} fraudes** "
    f"sin retener a ningún cliente honesto ({f_int(t['fp'])} falsos positivos), con **{f_int(t['alerts_per_day'])} alertas por día** "
    f"y un ahorro del **{f_pct(t['savings_pct'], 2)}** del monto defraudado. La regla vigente de la plataforma ahorraba "
    f"{f_pct(model['test_metrics']['rule_isFlaggedFraud']['savings_pct'], 2)}. El punto medio del umbral se adoptó después de observar "
    f"la prueba: con el criterio original el ahorro fue {f_pct(model['test_metrics']['champion_upper_edge']['savings_pct'], 2)}, "
    "que es la cifra conservadora. La página **Modelo y evaluación** detalla la metodología y sus límites."
)
