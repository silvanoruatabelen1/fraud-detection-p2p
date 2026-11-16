"""Crea el esquema y carga el historial de demostración antes de levantar los workers de la API.

Corre una sola vez por arranque del contenedor, así varios workers no compiten por la carga inicial.
"""

import logging

from .db import init_db, make_engine, seed_history
from .settings import settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = make_engine(settings.database_url)
    init_db(engine)
    seed_history(engine, settings.demo_data_dir)
    engine.dispose()


if __name__ == "__main__":
    main()
