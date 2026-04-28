"""
Inicializa el esquema de la base de datos.

Se ejecuta una sola vez (o cada vez que cambie el modelo en Sprint 1):

    docker compose exec api python -m cip.db_init

En Sprint 2 esto lo sustituimos por Alembic, que sí soporta migraciones
incrementales (esto borra y recrea, no es apto para producción).
"""

import asyncio

from cip.db import Base, get_engine
from cip.logging_setup import configure_logging, get_logger

log = get_logger(__name__)


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        log.info("creating_tables")
        await conn.run_sync(Base.metadata.create_all)
    log.info("db_init_done")


def main() -> None:
    configure_logging()
    asyncio.run(init_db())


if __name__ == "__main__":
    main()
