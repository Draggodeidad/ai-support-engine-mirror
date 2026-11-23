"""Definición, carga y uso de los modelos (categoría y prioridad)."""

from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from preprocessing import normalize_text

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = BASE_DIR / "models" / "model.joblib"

CATEGORIES = ["ACCESS", "BUG", "FEATURE", "SECURITY"]
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def build_pipeline() -> Pipeline:
    """TF-IDF de palabras (1-2 gramas) + TF-IDF de caracteres (3-5 gramas) -> regresión logística.

    Los n-gramas de caracteres hacen al modelo tolerante a faltas de ortografía
    ("entar", "contrasena") y a variaciones de una misma raíz ("hackeo", "hackearon").
    class_weight="balanced" compensa las clases con menos ejemplos.
    """
    features = FeatureUnion(
        [
            ("words", TfidfVectorizer(preprocessor=normalize_text, ngram_range=(1, 2), sublinear_tf=True)),
            ("chars", TfidfVectorizer(preprocessor=normalize_text, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)),
        ]
    )
    return Pipeline(
        [
            ("features", features),
            ("classifier", LogisticRegression(max_iter=2000, class_weight="balanced", C=10)),
        ]
    )


def build_baseline_pipeline() -> Pipeline:
    """Línea base sin ajustes: TF-IDF de palabras (1-2 gramas) -> regresión logística."""
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2))),
            ("classifier", LogisticRegression(max_iter=1000)),
        ]
    )


PIPELINES = {
    "default": (build_pipeline, "TF-IDF (palabras 1-2 + caracteres 3-5) + LogisticRegression"),
    "baseline": (build_baseline_pipeline, "TF-IDF (palabras 1-2) + LogisticRegression (línea base)"),
}


def save_bundle(bundle: dict, path: Path = DEFAULT_MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)


def load_bundle(path: Path = DEFAULT_MODEL_PATH) -> dict:
    return joblib.load(path)


def predict(bundle: dict, message: str) -> dict:
    """Devuelve la clase más probable de cada modelo y su probabilidad."""
    result = {}
    for target in ("category", "priority"):
        model = bundle[target]
        probabilities = model.predict_proba([message])[0]
        best = probabilities.argmax()
        result[target] = str(model.classes_[best])
        result[f"{target}Confidence"] = round(float(probabilities[best]), 4)
    return result
