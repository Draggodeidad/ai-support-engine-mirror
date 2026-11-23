"""Entrena los modelos de categoría y prioridad y guarda el resultado en models/.

Uso (desde ml-service/):
    python train.py
    python train.py --data data/tickets.csv --out models/model.joblib
    python train.py --pipeline baseline   # guarda models/baseline.joblib + metrics-baseline.json

Evaluación:
  1. Validación cruzada estratificada (5 particiones) sobre el dataset.
  2. División 80/20 estratificada con classification_report y matriz de confusión.
  3. Los 17 casos de ../tests/cases.json, que NO se usan para entrenar: es el mismo
     conjunto con el que se comparan los motores tradicional y generativo.
Al final se entrena con el dataset completo y se guarda el modelo.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn import __version__ as sklearn_version
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

from model import BASE_DIR, CATEGORIES, DEFAULT_MODEL_PATH, PIPELINES, PRIORITIES, save_bundle
from preprocessing import normalize_text

DEFAULT_DATA_PATH = BASE_DIR / "data" / "tickets.csv"
EVAL_CASES_PATH = BASE_DIR.parent / "tests" / "cases.json"
LABELS = {"category": CATEGORIES, "priority": PRIORITIES}
SEED = 42


def load_dataset(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path, encoding="utf-8")
    missing = {"message", "category", "priority"} - set(data.columns)
    if missing:
        raise SystemExit(f"Faltan columnas en {path}: {sorted(missing)}")
    data = data.dropna(subset=["message", "category", "priority"])
    for target, allowed in LABELS.items():
        invalid = sorted(set(data[target]) - set(allowed))
        if invalid:
            raise SystemExit(f"Valores no permitidos en '{target}': {invalid}")
    return data


def check_no_leakage(data: pd.DataFrame, cases: list[dict]) -> None:
    """Los casos de evaluación no deben estar en el entrenamiento."""
    reserved = {normalize_text(c["message"]) for c in cases}
    leaked = [m for m in data["message"] if normalize_text(m) in reserved]
    if leaked:
        raise SystemExit(f"El dataset contiene casos reservados para evaluación: {leaked}")


def evaluate(data: pd.DataFrame, build_pipeline) -> dict:
    metrics = {}
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

    for target, labels in LABELS.items():
        print(f"\n{'=' * 60}\n{target.upper()}\n{'=' * 60}")
        scores = cross_val_score(build_pipeline(), data["message"], data[target], cv=folds, scoring="accuracy")
        print(f"Validación cruzada (5 particiones): {scores.mean():.3f} ± {scores.std():.3f}")

        x_train, x_test, y_train, y_test = train_test_split(
            data["message"], data[target], test_size=0.2, stratify=data[target], random_state=SEED
        )
        model = build_pipeline().fit(x_train, y_train)
        predictions = model.predict(x_test)
        present = [label for label in labels if label in set(y_test)]
        print("\nDivisión 80/20:")
        print(classification_report(y_test, predictions, labels=present, zero_division=0))
        matrix = confusion_matrix(y_test, predictions, labels=present)
        print("Matriz de confusión (filas = real, columnas = predicho):")
        print(pd.DataFrame(matrix, index=present, columns=present).to_string())

        metrics[target] = {
            "cvAccuracyMean": round(float(scores.mean()), 4),
            "cvAccuracyStd": round(float(scores.std()), 4),
            "holdoutAccuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "holdoutReport": classification_report(
                y_test, predictions, labels=present, zero_division=0, output_dict=True
            ),
            "holdoutConfusionMatrix": {"labels": present, "matrix": matrix.tolist()},
        }
    return metrics


def evaluate_cases(bundle: dict, cases: list[dict]) -> dict:
    """Exactitud sobre tests/cases.json con el modelo final (sin política de seguridad)."""
    rows = []
    for case in cases:
        category = str(bundle["category"].predict([case["message"]])[0])
        priority = str(bundle["priority"].predict([case["message"]])[0])
        expected = case["expected"]
        rows.append(
            {
                "id": case["id"],
                "expected": f"{expected['category']}/{expected['priority']}",
                "predicted": f"{category}/{priority}",
                "categoryCorrect": category == expected["category"],
                "priorityCorrect": priority == expected["priority"],
            }
        )

    def pct(key: str) -> float:
        return round(100 * sum(r[key] for r in rows) / len(rows), 1)

    print(f"\n{'=' * 60}\nCASOS DE EVALUACIÓN (tests/cases.json, sin política de seguridad)\n{'=' * 60}")
    for r in rows:
        mark = "✔" if r["categoryCorrect"] and r["priorityCorrect"] else "✘"
        print(f"#{r['id']:>2} esperado {r['expected']:<18} predicho {r['predicted']:<18} {mark}")
    summary = {
        "total": len(rows),
        "categoryAccuracyPct": pct("categoryCorrect"),
        "priorityAccuracyPct": pct("priorityCorrect"),
        "fullAccuracyPct": round(100 * sum(r["categoryCorrect"] and r["priorityCorrect"] for r in rows) / len(rows), 1),
    }
    print(
        f"Categoría {summary['categoryAccuracyPct']}% · Prioridad {summary['priorityAccuracyPct']}% · "
        f"Ambas {summary['fullAccuracyPct']}%"
    )
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena los modelos de clasificación de tickets")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--pipeline", choices=sorted(PIPELINES), default="default")
    args = parser.parse_args()

    # La línea base nunca escribe sobre el modelo ni las métricas que usa el servicio.
    is_default = args.pipeline == "default"
    out = args.out or (DEFAULT_MODEL_PATH if is_default else DEFAULT_MODEL_PATH.with_name(f"{args.pipeline}.joblib"))
    metrics_name = "metrics.json" if is_default else f"metrics-{args.pipeline}.json"
    build_pipeline, algorithm = PIPELINES[args.pipeline]

    data = load_dataset(args.data)
    cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8")) if EVAL_CASES_PATH.exists() else []
    check_no_leakage(data, cases)
    print(f"Dataset: {len(data)} filas")
    print(pd.crosstab(data["category"], data["priority"]).reindex(columns=PRIORITIES, fill_value=0).to_string())

    metrics = evaluate(data, build_pipeline)

    # Modelo final: se entrena con todo el dataset.
    bundle = {
        "category": build_pipeline().fit(data["message"], data["category"]),
        "priority": build_pipeline().fit(data["message"], data["priority"]),
        "metadata": {
            "trainedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rows": int(len(data)),
            "sklearnVersion": sklearn_version,
            "algorithm": algorithm,
        },
    }
    if cases:
        metrics["evaluationCases"] = evaluate_cases(bundle, cases)

    save_bundle(bundle, out)
    metrics_path = out.parent / metrics_name
    metrics_path.write_text(
        json.dumps({**bundle["metadata"], **metrics}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nModelo guardado en {out}\nMétricas guardadas en {metrics_path}")


if __name__ == "__main__":
    main()
