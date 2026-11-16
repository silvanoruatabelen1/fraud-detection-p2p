# 0005 · Conjunto de demostración con pesos e historial exacto

**Estado:** aceptada

## Contexto
La plataforma tiene que funcionar sin el CSV de 470 MB. Reproducir días completos por HTTP implicaría cientos de miles de operaciones, y una muestra ingenua rompería el historial del destino.

## Decisión
- **Tráfico a reproducir:** todos los fraudes de riesgo de los días 16 a 18 y el 5% de las legítimas. Cada fila lleva su peso de muestreo, de 1 para los fraudes y 20 para las legítimas.
- **Historial de fondo:** todas las demás operaciones hacia esos destinos desde 168 h antes. Se cargan como historial, sin decisiones asociadas.
- **Reponderación:** los indicadores y el PSI se reponderan con los pesos de muestreo.

## Consecuencias
- El conjunto ocupa unos 3 MB.
- Los indicadores estiman volúmenes reales, y el historial que ve la API es exactamente el del entrenamiento.
- La sobrerrepresentación de fraudes está declarada en cada panel.
