# 0004 · API sin estado con historial desde la base de datos

**Estado:** aceptada

## Contexto
Dos atributos dependen de lo que recibió la cuenta de destino en las 168 h anteriores. Mantener ese historial en la memoria del proceso impide escalar con varios workers y se pierde al reiniciar.

## Decisión
- **Fuente del historial:** cada puntuación consulta Postgres, que es la fuente de verdad. La consulta suma las operaciones hacia el destino con `step` en [t − 168, t), y un índice por (destino, step) la mantiene en milisegundos.
- **Procesamiento por lotes:** se agrupan por hora. Todas las operaciones de una hora ven el mismo historial y se insertan después de puntuarse.
- **Una sola función de atributos:** la API usa `fraud_p2p.features.build_features`, la misma que el entrenamiento.

## Consecuencias
- Un test de paridad reproduce 18.748 operaciones reales a través de la API y exige el mismo puntaje que fuera de línea, con una diferencia menor a 1e-9, en SQLite y en Postgres.
- La API escala horizontalmente. El esquema y la carga inicial corren en un paso de `bootstrap`, antes de levantar los workers.
