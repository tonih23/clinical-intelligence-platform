"""Configuración global de pytest."""

import sys
from pathlib import Path

# Permite importar `cip` sin instalar el paquete (útil en CI mínimo)
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
