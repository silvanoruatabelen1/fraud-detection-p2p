# Data card · PaySim

| | |
|---|---|
| **Fuente** | Lopez-Rojas, E. A., Elmir, A. y Axelsson, S. (2016). *PaySim: A financial mobile money simulator for fraud detection.* 28th European Modeling and Simulation Symposium. Publicado en Kaggle (`ealaxi/paysim1`). |
| **Naturaleza** | Sintético. Agentes simulados a partir de un mes de registros de un servicio de dinero móvil africano. |
| **Tamaño** | 6.362.620 operaciones, 743 pasos horarios (31 días) y 11 columnas. |
| **Etiqueta** | `isFraud`: 8.213 fraudes (0,129%). |
| **Subespacio de riesgo** | TRANSFER y CASH_OUT: 2.770.409 operaciones con prevalencia de 0,296%. Los otros tipos no tienen fraude. |
| **Regla heredada** | `isFlaggedFraud`: 16 alertas en 31 días; detecta el 0,195% de los fraudes. |

## Calidad y decisiones de curación

- **Integridad:** no hay nulos ni duplicados, ni exactos ni por clave.
- **Precisión de los montos:** se leen en `float64`. En `float32` cambia el centavo del 20,5% de los montos, y la firma principal se mide al centavo.
- **Discrepancia contable:** es del 90,51% en las legítimas y baja al 0,41% al reconocer que el simulador lleva el saldo a 0 cuando el monto lo supera.
- **Valores extremos:** se conservan y se atenúan con `log10(1 + x)`, porque la cola de Tukey reúne el 41,92% de los fraudes.
- **Monto de 10 millones:** no es exclusivo del fraude. Hay 2.920 legítimas con ese monto, concentradas en los días 13 y 14. Solo es exclusivo el tramo retirado de una cuenta con saldo suficiente.
- **Volumen y prevalencia:** el volumen legítimo cae de unas 151.000 a 31.600 operaciones diarias entre las dos quincenas. Por eso la prevalencia de prueba (0,83%) cuadruplica la de entrenamiento.

## Capas del pipeline

| Capa | Archivo | Contenido |
|---|---|---|
| Bronce | `data/bronze/paysim.parquet` | El CSV tipado y validado contra un contrato de esquema. |
| Plata | `data/silver/paysim_curada.parquet` | Orden cronológico estable más el indicador de destino comerciante. |
| Oro | `data/gold/atributos_riesgo.parquet` | Subespacio de riesgo con los 12 atributos, la etiqueta y los metadatos. |

## Conjunto de demostración (`data/demo/`)

- **`replay.parquet`.** Contiene todos los fraudes de riesgo de los días 16 a 18 (840) y una muestra del 5% de las legítimas, en total 18.748 operaciones. Cada fila lleva su peso de muestreo para reponderar los indicadores y el puntaje esperado del campeón para la prueba de paridad.
- **`history_seed.parquet`.** Contiene las 87.176 operaciones restantes hacia esos destinos desde 168 h antes. Con ellas, el historial que la API calcula desde la base coincide exactamente con el del entrenamiento.

## Licencia y uso

PaySim es un dataset sintético de uso académico. Este repositorio no redistribuye el CSV completo: `make data` lo descarga desde Kaggle.
