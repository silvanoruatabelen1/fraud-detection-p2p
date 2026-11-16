# Model card · Detector de fraude P2P

## Uso previsto

El modelo puntúa transferencias (TRANSFER) y retiros en efectivo (CASH_OUT) de una billetera móvil en el momento de autorizarlos. El puntaje se convierte en una de tres acciones:

| Nivel | Puntaje (log-odds) | Acción |
|---|---|---|
| Rojo | ≥ −1,456 | Retener los fondos y derivar a un analista |
| Ámbar | entre −9,148 y −1,456 | Verificación automática (código o huella) |
| Verde | < −9,148 | Aprobar sin fricción |

Los demás tipos de operación (PAYMENT, CASH_IN y DEBIT) no tuvieron ningún fraude en los datos: se aprueban sin puntuar, pero se registran porque alimentan el historial de la cuenta de destino.

**No está pensado para:**

- decidir sin revisión humana una retención definitiva;
- usarse sobre datos reales sin reentrenar ni volver a validar;
- inferir características de las personas.

## Modelos

| Rol | Modelo | Hiperparámetros | Umbral (log-odds) |
|---|---|---|---|
| Campeón (decide) | Regresión logística con escalado estándar | C = 0,01, sin reponderar, `newton-cholesky` | −1,456 |
| Retador (sombra) | XGBoost | profundidad 3, tasa 0,05, 300 árboles, submuestreo 0,8 | −1,315 |
| Retador entrenado con ataques (sombra) | XGBoost, mismos hiperparámetros | 4 copias sintéticas por fraude de entrenamiento con retiros del 50% al 99% | −1,999 |
| Centinela (sombra) | Regresión logística sin las dos firmas exactas | C = 0,01 | −3,018 |

**Cómo se eligió el campeón.** Se compararon seis familias (logística, LDA, QDA, CART, Random Forest y XGBoost) en 27 configuraciones, con validación cruzada temporal de origen móvil y PR-AUC. Todas quedaron dentro de un error estándar de la mejor (0,99783 a 0,99805). Se aplicó la regla de un error estándar, declarada antes de mirar resultados: entre modelos indistinguibles gana el más simple.

## Atributos

Son 12, todos conocidos al autorizar:

- **Operación:** tipo, monto, saldo previo de origen y la relación monto/saldo.
- **Indicadores al centavo:** cuenta de origen sin saldo, pide más que el saldo y vacía la cuenta.
- **Tramo de 10 millones** con saldo suficiente.
- **Hora del día**, en codificación cíclica.
- **Historial del destino:** operaciones y monto recibidos en [t − 168 h, t).

Se excluyen los saldos posteriores, que filtran la etiqueta: el saldo final de origen es 0 en el 98,05% de los fraudes. También se excluyen los identificadores de cuenta.

## Datos de evaluación

Período de prueba: días 16 a 31, con 505.511 operaciones de riesgo y 4.196 fraudes. Ese período nunca se usó para elegir el modelo ni sus hiperparámetros. El umbral se eligió en validación (días 13 a 15).

## Métricas en prueba

Cupo de 1.000 revisiones por día, con una cola diaria que atiende las alertas por orden de llegada.

| Métrica | Campeón |
|---|---|
| Fraudes detenidos | 4.193 de 4.196 (sensibilidad 99,93%; IC 95% de Wilson: 99,79% a 99,98%) |
| Falsos positivos | 0 entre 501.315 legítimas |
| Alertas por día | 262,1 |
| PR-AUC | 0,99951 |
| Brier | 5,94 × 10⁻⁶ |
| Ahorro neto | 99,64% del monto defraudado (98,42% con el criterio de umbral original) |

## Limitaciones conocidas

1. **Datos simulados.** Las regularidades más fuertes son reglas del simulador PaySim. Una regla transparente de dos firmas logra el mismo resultado que el modelo.
2. **Dependencia de una igualdad exacta.**
   - Con cualquier retiro parcial, incluso dejando un centavo, el campeón detecta el 0,3% de los fraudes.
   - El XGBoost entrenado con ataques llega al 86,9% ante retiros del 90%, pero cae al 7,6% y al 1,0% con retiros del 30% y del 10%, que no vio al entrenarse.
   - El 10% de las legítimas pide menos que el saldo: un robo chico no se distingue de ellas sin señales que PaySim no registra (dispositivo, ubicación, velocidad).
3. **Umbral revisado tras la prueba.** El criterio del punto medio se adoptó después de observar la prueba. La cifra conservadora es 98,42%. Un control con datos anteriores a la prueba no alcanzaba para elegir entre los dos criterios.
4. **Costos supuestos.** Multiplicar los costos de revisión y de fricción hasta por 20 deja el ahorro entre 99,26% y 99,69%. Lo que sí lo cambia es el cupo: con 50 revisiones por día baja a 31,79%.
5. **Dependencia horaria de los modelos de control.** Si todo el tráfico legítimo ocurriera de madrugada, marcarían más de 1.400 operaciones por día, así que sus alertas deben leerse por franja horaria.

## Equidad

En prueba no hubo falsos positivos en ningún segmento. Con cero eventos, la tasa de falsos positivos hacia destinos sin historial queda acotada en 28,3 por millón de legítimas (Wilson, 95%).

**Resguardos propuestos:**

- revisión humana de toda retención;
- explicación al cliente basada en los factores del modelo;
- monitoreo de falsos positivos por segmento;
- uso del historial del destino solo como atenuante.

## Monitoreo y reentrenamiento

- **Deriva:** PSI por atributo y del puntaje, sobre ventanas de días completos. La deriva esperada está en el historial del destino, porque en la segunda quincena cae el volumen legítimo.
- **Disparador de reentrenamiento:** que los modelos de control marquen fraudes que el campeón aprobó y luego se confirmen. Es la señal de que el atacante cambió de táctica.
