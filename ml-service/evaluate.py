"""Evalúa un pipeline de categoría con una división 80/20 estratificada y predice un mensaje nuevo.

Uso (desde ml-service/):
    python evaluate.py
    python evaluate.py --pipeline default
    python evaluate.py --message "No puedo iniciar sesión"

No guarda nada: el modelo que usa la API se sigue generando con train.py.
"""

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from model import PIPELINES
from train import DEFAULT_DATA_PATH, SEED, load_dataset

DEFAULT_MESSAGE = "Encontré datos de otros clientes"


def fit_holdout(data: pd.DataFrame, build_pipeline) -> tuple[Pipeline, pd.Series, pd.Series]:
    """Entrena con el 80% y devuelve el modelo junto con el 20% reservado."""
    X_train, X_test, y_train, y_test = train_test_split(
        data["message"], data["category"], test_size=0.2, stratify=data["category"], random_state=SEED
    )
    model = build_pipeline().fit(X_train, y_train)
    return model, X_test, y_test


def print_evaluation(model: Pipeline, X_test: pd.Series, y_test: pd.Series) -> None:
    predictions = model.predict(X_test)
    print(classification_report(y_test, predictions, zero_division=0))
    print("Matriz de confusión (filas = real, columnas = predicho):", list(model.classes_))
    print(confusion_matrix(y_test, predictions, labels=model.classes_))


def predict_message(model: Pipeline, message: str) -> tuple[str, float]:
    """Devuelve la categoría y su probabilidad, un score aproximado (no está calibrado)."""
    new_message = [message]
    category = model.predict(new_message)[0]
    confidence = model.predict_proba(new_message).max()
    return str(category), round(float(confidence), 3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa el clasificador de categoría")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--pipeline", choices=sorted(PIPELINES), default="baseline")
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    args = parser.parse_args()

    build_pipeline, _algorithm = PIPELINES[args.pipeline]
    model, X_test, y_test = fit_holdout(load_dataset(args.data), build_pipeline)
    print_evaluation(model, X_test, y_test)

    category, confidence = predict_message(model, args.message)
    print("\nMensaje:", args.message)
    print("Categoría:", category)
    print("Score aproximado:", confidence)


if __name__ == "__main__":
    main()
