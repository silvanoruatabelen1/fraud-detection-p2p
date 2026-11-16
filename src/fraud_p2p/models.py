"""Definición de los modelos. Los hiperparámetros son los elegidos con validación cruzada temporal
(regla de un error estándar) en el notebook NB2; acá solo se reentrenan."""

from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42

CHAMPION_PARAMS = {"C": 0.01, "class_weight": None}
CHALLENGER_PARAMS = {"max_depth": 3, "learning_rate": 0.05, "n_estimators": 300}


def make_champion() -> Pipeline:
    """Regresión logística regularizada: explicable, calibrable y de latencia mínima."""
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=CHAMPION_PARAMS["C"],
            class_weight=CHAMPION_PARAMS["class_weight"],
            solver="newton-cholesky",
            max_iter=1000,
        ),
    )


def make_challenger() -> xgb.XGBClassifier:
    """XGBoost poco profundo: el mejor ensamble, corre en sombra."""
    return xgb.XGBClassifier(
        n_estimators=CHALLENGER_PARAMS["n_estimators"],
        max_depth=CHALLENGER_PARAMS["max_depth"],
        learning_rate=CHALLENGER_PARAMS["learning_rate"],
        subsample=0.8,
        colsample_bytree=0.8,
        tree_method="hist",
        n_jobs=-1,
        random_state=SEED,
        eval_metric="aucpr",
    )


def score(model, X: pd.DataFrame) -> np.ndarray:
    """Puntaje en log-odds (margen). Es la escala en la que se fijan los umbrales."""
    if isinstance(model, xgb.XGBClassifier):
        return model.predict(X, output_margin=True)
    return model.decision_function(X)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=np.float64)))
