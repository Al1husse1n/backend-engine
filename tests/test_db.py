import pytest
from sqlalchemy import inspect

from app.db import (
    Base,
    _engine_connect_args,
    _engine_kwargs,
    _normalize_database_url,
    _uses_transaction_pooler,
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


def test_session_pooler_port_5432_is_not_the_transaction_pooler():
    url = _normalize_database_url(
        "postgresql://postgres.example:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
    )
    assert _uses_transaction_pooler(url) is False
    assert "prepare_threshold" not in _engine_connect_args(url)
    assert _engine_kwargs(url)["pool_pre_ping"] is True


def test_password_with_url_special_characters_keeps_real_port():
    password = "bthK/secr#et?query:p@ss"
    session = _normalize_database_url(
        "postgresql://postgres.example:"
        f"{password}@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
    )
    transaction = _normalize_database_url(
        "postgres://postgres.example:"
        f"{password}@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    )
    assert _uses_transaction_pooler(session) is False
    assert "prepare_threshold" not in _engine_connect_args(session)
    assert _engine_kwargs(session)["pool_pre_ping"] is True
    assert _uses_transaction_pooler(transaction) is True
    assert _engine_connect_args(transaction)["prepare_threshold"] is None

    engine = create_db_engine(session)
    assert engine.url.port == 5432
    assert engine.pool._pre_ping is True
    engine.dispose()


def test_non_numeric_port_is_rejected():
    url = "postgresql+psycopg://user:pass@db.example:bthK/postgres"
    with pytest.raises(ValueError, match="Invalid database URL port 'bthK'"):
        _uses_transaction_pooler(url)


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