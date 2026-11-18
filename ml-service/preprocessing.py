"""Normalización de texto, equivalente a normalizeText() del motor tradicional (Node).

Minúsculas, sin tildes ni signos de puntuación y espacios simples, para que
"Contraseña", "contraseña" y "CONTRASENA" generen las mismas características.
"""

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _NON_ALNUM.sub(" ", text)
    return _SPACES.sub(" ", text).strip()
