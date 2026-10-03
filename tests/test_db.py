from sqlalchemy import inspect

from app.db import (
    Base,
    _engine_connect_args,
    _engine_kwargs,
    _normalize_database_url,
    create_db_engine,
)
from app.models import Event  # noqa: F401


def test_postgres_urls_use_psycopg_driver():
    assert _normalize_database_url("postgres://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )
    assert _normalize_database_url("postgresql://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )


def test_explicit_sqlalchemy_dialects_are_left_unchanged():
    psycopg = "postgresql+psycopg://user:pass@host/db"
    psycopg2 = "postgresql+psycopg2://user:pass@host/db"
    assert _normalize_database_url(psycopg) == psycopg
    assert _normalize_database_url(psycopg2) == psycopg2
    assert _normalize_database_url("sqlite:///./data/app.db") == "sqlite:///./data/app.db"


def test_transaction_pooler_disables_prepared_statements():
    pooled = _normalize_database_url("postgres://user:pass@aws-0.pooler.supabase.com:6543/postgres")
    direct = _normalize_database_url("postgresql://user:pass@db.example:5432/postgres")
    assert _engine_connect_args(pooled)["prepare_threshold"] is None
    assert "prepare_threshold" not in _engine_connect_args(direct)
    assert _engine_kwargs(pooled)["pool_pre_ping"] is True
    assert _engine_kwargs(direct)["pool_pre_ping"] is True


def test_sqlite_does_not_get_postgres_pool_options(tmp_path):
    url = f"sqlite:///{tmp_path / 'local.db'}"
    assert "prepare_threshold" not in _engine_connect_args(url)
    assert "pool_pre_ping" not in _engine_kwargs(url)
    assert _engine_connect_args(url)["check_same_thread"] is False

    engine = create_db_engine(url)
    Base.metadata.create_all(bind=engine)
    assert "events" in inspect(engine).get_table_names()
    assert engine.pool._pre_ping is False
    engine.dispose()