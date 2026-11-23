import pytest

from evaluate import DEFAULT_MESSAGE, fit_holdout, predict_message, print_evaluation
from model import build_baseline_pipeline
from train import DEFAULT_DATA_PATH, load_dataset


@pytest.fixture(scope="module")
def holdout():
    return fit_holdout(load_dataset(DEFAULT_DATA_PATH), build_baseline_pipeline)


def test_fit_holdout_reserves_a_stratified_20_percent(holdout):
    model, X_test, y_test = holdout
    assert len(X_test) == 48
    assert y_test.value_counts().to_dict() == {label: 12 for label in model.classes_}


def test_print_evaluation_shows_report_and_matrix(holdout, capsys):
    print_evaluation(*holdout)
    output = capsys.readouterr().out
    assert "precision" in output
    assert "Matriz de confusión" in output
    for label in holdout[0].classes_:
        assert label in output


def test_predict_message_returns_top_class_and_its_probability(holdout):
    model = holdout[0]
    category, confidence = predict_message(model, DEFAULT_MESSAGE)
    probabilities = model.predict_proba([DEFAULT_MESSAGE])[0]
    assert category == model.classes_[probabilities.argmax()]
    assert confidence == round(float(probabilities.max()), 3)
