# 0001 · Validación temporal y regla de un error estándar

**Estado:** aceptada

## Contexto
Las operaciones tienen orden temporal y la proporción de fraude cambia: en la segunda quincena cae el volumen legítimo. Una partición aleatoria mezclaría pasado y futuro, y daría métricas optimistas.

## Decisión
- **Partición cronológica:** entrenamiento con los días 1 a 12, validación con los días 13 a 15 y prueba con los días 16 a 31. La prueba no participa de ninguna elección de modelo ni de hiperparámetros.
- **Comparación de modelos:** seis familias con validación cruzada de origen móvil en tres pliegues, medidas con PR-AUC, que es la métrica adecuada con 0,3% de positivos.
- **Criterio de elección:** la regla de un error estándar con un orden de complejidad declarado de antemano. Entre modelos indistinguibles, gana el más simple.

## Consecuencias
- Las seis familias quedaron dentro de un error estándar, con PR-AUC de 0,99783 a 0,99805 y un error estándar de 0,00105. Gana la regresión logística, que además es explicable y calibrable y puntúa en microsegundos.
- XGBoost queda como retador en sombra.
