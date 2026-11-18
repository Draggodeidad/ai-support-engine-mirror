import sys
from pathlib import Path

# Permite importar app, model y preprocessing desde ml-service/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
