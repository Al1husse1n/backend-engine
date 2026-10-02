from sqlalchemy import inspect

from app.db import Base, _normalize_database_url, create_db_engine
from app.models import Event  # noqa: F401


def test_postgres_urls_use_psycopg_driver():
    assert _normalize_database_url("postgres://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )
    assert _normalize_database_url("postgresql://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )


def test_sqlite_support_remains_available_for_local_development(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'local.db'}")
    Base.metadata.create_all(bind=engine)

    assert "events" in inspect(engine).get_table_names()
    engine.dispose()