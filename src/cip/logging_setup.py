"""
Logging estructurado.

structlog produce logs en formato JSON, que son los que entienden
herramientas como Datadog, Loki o ELK en producción. En desarrollo
podemos imprimirlos como texto bonito con ConsoleRenderer.

Regla: nunca uses `print()`. Siempre `log = get_logger(__name__)`.
"""

import logging
import sys
from typing import cast

import structlog

from cip.config import get_settings


def configure_logging() -> None:
    """Configura structlog. Llamar una sola vez al arrancar la aplicación."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Logging de la stdlib redirigido a structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Devuelve un logger nombrado."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
