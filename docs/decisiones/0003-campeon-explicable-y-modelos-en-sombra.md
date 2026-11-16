# 0003 · Campeón explicable y modelos en sombra

**Estado:** aceptada

## Contexto
La detección depende de una igualdad exacta entre el monto y el saldo. Con cualquier retiro parcial, el campeón detecta el 0,3% de los fraudes. Entrenar con ataques sintéticos mejora la detección ante retiros grandes, pero empeora la precisión y no generaliza a retiros chicos.

## Decisión
- **El campeón sigue siendo la logística.** Ascender al XGBoost por su desempeño ante ataques diseñados por el propio equipo sería elegir con la prueba.
- **Tres modelos corren en sombra, sin efecto sobre la decisión:**
  - el retador XGBoost;
  - el XGBoost entrenado con retiros parciales sintéticos;
  - un centinela sin las firmas exactas.
- **Se registran sus alertas.** Cuando marcan una operación que el campeón aprobó, la decisión queda señalada como posible cambio de táctica.

## Consecuencias
- Si esas señales se confirman como fraude, corresponde reentrenar con los casos nuevos.
- Los modelos de control generan muchas alertas sobre legítimas, sobre todo de madrugada. Por eso no deciden y sus alertas se leen por franja horaria.
