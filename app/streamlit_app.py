"""Plataforma antifraude PagoDirecto: simulador, operaciones, paneles de negocio y monitoreo.

streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="PagoDirecto · Antifraude P2P", page_icon="🛡️", layout="wide")

pages = {
    "Producto": [
        st.Page("views/inicio.py", title="Inicio", icon="🏠", default=True),
        st.Page("views/simulador.py", title="Simulador de operaciones", icon="🧪"),
    ],
    "Operación": [
        st.Page("views/operaciones.py", title="Cola de alertas", icon="🚨"),
        st.Page("views/capacidad.py", title="Capacidad del equipo", icon="👥"),
    ],
    "Negocio": [
        st.Page("views/negocio.py", title="Riesgo y finanzas", icon="💰"),
        st.Page("views/experiencia.py", title="Experiencia del cliente", icon="🤝"),
    ],
    "Modelo": [
        st.Page("views/monitoreo.py", title="Monitoreo y deriva", icon="📡"),
        st.Page("views/modelo.py", title="Modelo y evaluación", icon="📊"),
    ],
}
st.navigation(pages).run()
