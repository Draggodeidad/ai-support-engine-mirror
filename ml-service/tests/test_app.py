from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import create_app
from model import build_pipeline, predict, save_bundle
from preprocessing import normalize_text

TINY = pd.DataFrame(
    {
        "message": [
            "no puedo iniciar sesion con mi contrasena",
            "olvide mi clave y la cuenta esta bloqueada",
            "la pagina muestra error 500 al guardar",
            "la aplicacion se cierra sola al abrir reportes",
            "me gustaria que agregaran modo oscuro",
            "seria bueno exportar a excel",
            "alguien entro a mi cuenta sin autorizacion",
            "encontre una inyeccion sql en el formulario",
        ],
        "category": ["ACCESS", "ACCESS", "BUG", "BUG", "FEATURE", "FEATURE", "SECURITY", "SECURITY"],
        "priority": ["MEDIUM", "MEDIUM", "HIGH", "MEDIUM", "LOW", "LOW", "CRITICAL", "CRITICAL"],
    }
)


@pytest.fixture(scope="module")
def model_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("models") / "model.joblib"
    bundle = {
        "category": build_pipeline().fit(TINY["message"], TINY["category"]),
        "priority": build_pipeline().fit(TINY["message"], TINY["priority"]),
        "metadata": {"rows": len(TINY)},
    }
    save_bundle(bundle, path)
    return path


@pytest.fixture()
def client(model_path):
    with TestClient(create_app(model_path)) as c:
        yield c


def test_normalize_text():
    assert normalize_text("  ¡CONTRASEÑA   incorrecta! ") == "contrasena incorrecta"


def test_health_reports_model(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["modelLoaded"] is True


def test_predict_returns_contract(client):
    res = client.post("/predict", json={"message": "No puedo iniciar sesión, olvidé mi contraseña"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"category", "priority", "categoryConfidence", "priorityConfidence"}
    assert body["category"] == "ACCESS"
    assert 0 <= body["categoryConfidence"] <= 1


@pytest.mark.parametrize(
    "payload",
    [{}, {"message": "ab"}, {"message": "x" * 2001}, {"message": 123}, {"message": "hola mundo", "extra": 1}],
)
def test_predict_rejects_invalid_input(client, payload):
    res = client.post("/predict", json=payload)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_REQUEST"


def test_predict_without_model_returns_503(tmp_path):
    with TestClient(create_app(tmp_path / "missing.joblib")) as c:
        assert c.get("/health").json()["modelLoaded"] is False
        res = c.post("/predict", json={"message": "hola mundo"})
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "MODEL_NOT_LOADED"


def test_predict_helper_confidence_is_max_probability(model_path):
    from model import load_bundle

    result = predict(load_bundle(model_path), "encontré una inyección sql")
    assert result["category"] == "SECURITY"
    assert 0.25 < result["categoryConfidence"] <= 1
