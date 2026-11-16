# Notebooks de investigación

| Notebook | Contenido |
|---|---|
| `NB1_Encuadre_EDA_Limpieza.ipynb` | Encuadre de negocio, calidad de datos, exploración, contrastes estadísticos y registro de 14 decisiones de curación. |
| `NB2_Modelado_Umbral_Evaluacion.ipynb` | Atributos ex ante, partición temporal, validación cruzada de seis familias, umbral económico, evaluación en prueba, ablación, batería de ataques, explicabilidad, latencia y equidad. |

Los notebooks se conservan ejecutados, con sus salidas, tal como se entregaron. Para volver a ejecutarlos:

1. Ubicar `p2p.csv` en `data/raw/` (`make data`).
2. Ejecutar NB1 y después NB2 desde la raíz del repositorio o desde esta carpeta, con el grupo de dependencias `analysis` (`uv sync --group analysis`).

El código de producción en `src/fraud_p2p/` reimplementa las mismas transformaciones como funciones probadas. `make pipeline` reproduce los modelos, los umbrales y las métricas del NB2 con precisión completa.
