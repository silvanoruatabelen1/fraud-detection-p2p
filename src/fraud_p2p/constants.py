"""Constantes del dominio. Cambiarlas cambia el modelo: están versionadas junto al código."""

from __future__ import annotations

RAW_COLUMNS: dict[str, str] = {
    "step": "int16",
    "type": "category",
    "amount": "float64",
    "nameOrig": "string",
    "oldbalanceOrg": "float64",
    "newbalanceOrig": "float64",
    "nameDest": "string",
    "oldbalanceDest": "float64",
    "newbalanceDest": "float64",
    "isFraud": "int8",
    "isFlaggedFraud": "int8",
}

TRANSACTION_TYPES: tuple[str, ...] = ("CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER")
RISK_TYPES: tuple[str, ...] = ("TRANSFER", "CASH_OUT")  # todo el fraude de PaySim ocurre aquí

HISTORY_WINDOW_H = 168  # ventana causal del historial del destino: [t - 168 h, t)
TRANCHE_10M = 10_000_000.0  # el simulador fracciona los robos grandes en tramos de 10 millones

N_STEPS = 743
TRAIN_END_STEP = 288  # días 1 a 12
VALID_END_STEP = 360  # días 13 a 15; la prueba son los días 16 a 31

FEATURES: list[str] = [
    "es_transfer",
    "log_monto",
    "log_saldo_orig",
    "emisor_sin_saldo",
    "monto_excede_saldo",
    "log_ratio_monto_saldo",
    "marca_vaciamiento",
    "tramo_10m_con_saldo",
    "hora_sen",
    "hora_cos",
    "dest_ops_previas_log",
    "dest_monto_previo_log",
]

# El centinela se entrena sin las dos firmas exactas para detectar cambios de táctica del atacante.
SIGNATURE_FEATURES: list[str] = ["marca_vaciamiento", "tramo_10m_con_saldo"]
SENTINEL_FEATURES: list[str] = [f for f in FEATURES if f not in SIGNATURE_FEATURES]

FEATURE_LABELS: dict[str, str] = {
    "es_transfer": "Es transferencia (no retiro)",
    "log_monto": "Monto",
    "log_saldo_orig": "Saldo de la cuenta de origen",
    "emisor_sin_saldo": "Cuenta de origen sin saldo",
    "monto_excede_saldo": "Pide más que el saldo",
    "log_ratio_monto_saldo": "Relación monto / saldo",
    "marca_vaciamiento": "Vacía la cuenta al centavo",
    "tramo_10m_con_saldo": "Tramo de 10 M con saldo suficiente",
    "hora_sen": "Hora del día (componente seno)",
    "hora_cos": "Hora del día (componente coseno)",
    "dest_ops_previas_log": "Operaciones previas del destino (168 h)",
    "dest_monto_previo_log": "Monto previo recibido por el destino (168 h)",
}


def day_of_step(step):
    """Día de la simulación (1 a 31) a partir del step horario (1 a 743)."""
    return (step - 1) // 24 + 1
