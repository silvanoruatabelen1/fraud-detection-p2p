"""Cliente de la API, formato rioplatense y componentes visuales compartidos por las páginas."""

from __future__ import annotations

import os
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")

FRAUD, LEGIT, NEUTRAL, ACCENT, OK, MUTED = "#B42318", "#1B365D", "#5C768D", "#D97706", "#0F766E", "#98A2B3"
TIER_COLOR = {"rojo": FRAUD, "ambar": ACCENT, "verde": OK}
LABELS = {
    "es_transfer": "Es transferencia",
    "log_monto": "Monto",
    "log_saldo_orig": "Saldo de origen",
    "emisor_sin_saldo": "Origen sin saldo",
    "monto_excede_saldo": "Pide más que el saldo",
    "log_ratio_monto_saldo": "Relación monto/saldo",
    "marca_vaciamiento": "Vacía la cuenta al centavo",
    "tramo_10m_con_saldo": "Tramo de 10 M con saldo",
    "hora_sen": "Hora (seno)",
    "hora_cos": "Hora (coseno)",
    "dest_ops_previas_log": "Operaciones previas del destino",
    "dest_monto_previo_log": "Monto previo del destino",
}
TIER_LABEL = {"rojo": "Rojo · retener", "ambar": "Ámbar · verificar", "verde": "Verde · aprobar"}

pio.templates["fd"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Inter, system-ui, sans-serif", size=13, color="#1F2937"),
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        separators=",.",
        colorway=[LEGIT, FRAUD, ACCENT, OK, NEUTRAL, "#7A5AF8"],
        xaxis=dict(showgrid=False, linecolor="#D0D5DD"),
        yaxis=dict(gridcolor="#EAECF0", zeroline=False),
        margin=dict(l=10, r=10, t=40, b=10),
        hoverlabel=dict(bgcolor="white"),
        legend=dict(orientation="h", y=-0.18, x=0),
    )
)
pio.templates.default = "simple_white+fd"


# ---------------------------------------------------------------- API
class ApiError(RuntimeError):
    pass


def api(method: str, path: str, **kwargs) -> Any:
    try:
        r = requests.request(method, f"{API_URL}{path}", timeout=60, **kwargs)
    except requests.RequestException as e:
        raise ApiError(f"No se pudo conectar con la API en {API_URL}") from e
    if not r.ok:
        raise ApiError(f"La API respondió {r.status_code}: {r.text[:300]}")
    return r.json()


@st.cache_data(ttl=5, show_spinner=False)
def get(path: str, **params) -> Any:
    return api("GET", path, params=params or None)


def guard(fn):
    """Muestra un aviso claro si la API no está disponible, en lugar de un traceback."""
    try:
        return fn()
    except ApiError as e:
        st.error(f"{e}. Levantá el sistema con `docker compose up` o `make api`.")
        st.stop()


# ---------------------------------------------------------------- formato
def f_int(x: float | None) -> str:
    return "—" if x is None else f"{round(x):,}".replace(",", ".")


def f_num(x: float | None, d: int = 1) -> str:
    return "—" if x is None else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def f_pct(x: float | None, d: int = 1) -> str:
    return "—" if x is None else f"{f_num(x, d)}%"


def f_money(x: float | None) -> str:
    if x is None:
        return "—"
    for div, suf in ((1e9, " mil M"), (1e6, " M"), (1e3, " mil")):
        if abs(x) >= div:
            return f"{f_num(x / div, 1)}{suf} u.m."
    return f"{f_num(x, 0)} u.m."


# ---------------------------------------------------------------- componentes
CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1280px;}
h1 {font-weight: 700; letter-spacing: -0.02em;}
.fd-kpi {background:#fff;border:1px solid #EAECF0;border-radius:12px;padding:16px 18px;height:100%;}
.fd-kpi .lbl {font-size:.80rem;color:#475467;margin-bottom:6px;}
.fd-kpi .val {font-size:1.65rem;font-weight:700;color:#101828;line-height:1.1;}
.fd-kpi .sub {font-size:.78rem;color:#667085;margin-top:6px;}
.fd-pill {display:inline-block;padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:600;color:#fff;}
.fd-verdict {border-radius:14px;padding:20px 22px;color:#fff;}
.fd-verdict .t {font-size:1.5rem;font-weight:700;}
.fd-verdict .a {font-size:1rem;opacity:.95;margin-top:4px;}
.fd-note {font-size:.85rem;color:#475467;}
</style>
"""


def setup(title: str, subtitle: str = "") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def kpi(col, label: str, value: str, sub: str = "", color: str | None = None) -> None:
    style = f"border-top:3px solid {color};" if color else ""
    col.markdown(
        f'<div class="fd-kpi" style="{style}"><div class="lbl">{label}</div>'
        f'<div class="val">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )


def pill(tier: str) -> str:
    return f'<span class="fd-pill" style="background:{TIER_COLOR[tier]}">{TIER_LABEL[tier]}</span>'


def contributions_chart(contrib: dict[str, float], labels: dict[str, str], height: int = 360) -> go.Figure:
    items = sorted(contrib.items(), key=lambda kv: kv[1])
    fig = go.Figure(
        go.Bar(
            x=[v for _, v in items],
            y=[labels.get(k, k) for k, _ in items],
            orientation="h",
            marker_color=[FRAUD if v > 0 else LEGIT for _, v in items],
            hovertemplate="%{y}: %{x:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=height,
        title="Aporte de cada atributo al puntaje (log-odds)",
        xaxis_title="← hacia legítima · hacia fraude →",
    )
    return fig


def demo_notice() -> None:
    st.info(
        "Datos de demostración: operaciones reales de PaySim de los días 16 a 18 (período de prueba). Están todos los "
        "fraudes y el 5% de las legítimas; los indicadores se reponderan por el peso de muestreo para estimar volúmenes reales.",
        icon="ℹ️",
    )
