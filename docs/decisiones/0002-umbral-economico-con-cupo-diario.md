# 0002 · Umbral económico con cupo diario

**Estado:** aceptada

## Contexto
Un umbral de 0,5 no tiene sentido económico. Cada alerta cuesta una revisión y cada cliente honesto retenido cuesta fricción. Además, el equipo de revisión tiene una capacidad limitada por día, no en promedio.

## Decisión
- **Función de ahorro:** ahorro = monto de los fraudes detenidos − 1.500 u.m. por alerta − 8.500 u.m. por cliente honesto retenido. Se evalúa en todos los umbrales posibles de validación.
- **Factibilidad:** un umbral es factible solo si **ningún día** supera el cupo de 1.000 revisiones.
- **Elección:** se elige el punto medio de la franja factible con al menos el 99,9% del ahorro máximo. Los bordes de la franja quedan fijados por una sola operación de validación, y el centro deja el mayor margen frente a lo no observado.
- **Evaluación:** en prueba, una cola diaria atiende las alertas por orden de llegada hasta completar el cupo.

## Consecuencias
- El criterio del punto medio se adoptó después de observar la prueba. Se declara así y se informa también el resultado con el criterio original: 98,42% de ahorro frente a 99,64%.
- El endpoint `/v1/economics/whatif` y la página «Riesgo y finanzas» vuelven a elegir el umbral cuando cambian los costos o el cupo.
