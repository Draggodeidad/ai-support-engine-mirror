"""Microservicio de Machine Learning: clasifica tickets de soporte con el modelo entrenado.

Arranque (desde ml-service/):
    uvicorn app:app --port 8000

El modelo se entrena aparte con `python train.py` y se carga una sola vez al iniciar.
No hay endpoint de entrenamiento: reentrenar desde una petición HTTP abierta permitiría
que cualquiera cambie el modelo.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from model import DEFAULT_MODEL_PATH, load_bundle, predict

logger = logging.getLogger("ml-service")
MAX_MESSAGE_LENGTH = 2000  # igual que el contrato de la API Node


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=3, max_length=MAX_MESSAGE_LENGTH)


class PredictResponse(BaseModel):
    category: Literal["ACCESS", "BUG", "FEATURE", "SECURITY"]
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    categoryConfidence: float = Field(ge=0, le=1)
    priorityConfidence: float = Field(ge=0, le=1)


def create_app(model_path: Path | None = None) -> FastAPI:
    path = Path(model_path or os.environ.get("ML_MODEL_PATH") or DEFAULT_MODEL_PATH)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            app.state.bundle = load_bundle(path)
            logger.info("Modelo cargado desde %s", path)
        except FileNotFoundError:
            app.state.bundle = None
            logger.warning("No existe el modelo en %s; ejecuta `python train.py`", path)
        yield

    app = FastAPI(title="AI Support ML Service", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body") or "(body)", "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_REQUEST", "message": "La solicitud no es válida", "details": details}},
        )

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, exc: Exception):
        logger.error("Error interno: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "Error interno del servidor"}}
        )

    @app.get("/health")
    def health(request: Request):
        bundle = request.app.state.bundle
        return {
            "status": "ok",
            "modelLoaded": bundle is not None,
            "model": bundle["metadata"] if bundle else None,
        }

    @app.post("/predict", response_model=PredictResponse)
    def predict_endpoint(body: PredictRequest, request: Request):
        bundle = request.app.state.bundle
        if bundle is None:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "MODEL_NOT_LOADED", "message": "El modelo no está entrenado"}},
            )
        return predict(bundle, body.message)

    return app


app = create_app()
