"""Create the schema if missing: `python -m splitkit.db.migrate`.

Every statement is CREATE ... IF NOT EXISTS, so running this before each
container start is safe. Schema *changes* to existing tables would need real
versioned migrations (e.g. Alembic); none exist yet because nothing has been
deployed with an older schema.
"""

from __future__ import annotations

import logging
import os

import psycopg

from splitkit.db.schema import create_schema

logger = logging.getLogger("splitkit.migrate")


def run(dsn: str, search_path: str | None = None) -> None:
    options = {"options": f"-c search_path={search_path}"} if search_path else {}
    with psycopg.connect(dsn, autocommit=True, **options) as conn:
        create_schema(conn)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    dsn = os.environ.get("SPLITKIT_PG_DSN")
    if not dsn:
        logger.error("SPLITKIT_PG_DSN is not set")
        return 1
    try:
        run(dsn)
    except psycopg.OperationalError as exc:
        logger.error("could not reach the database: %s", exc)
        return 1
    logger.info("schema is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
