from urllib.parse import quote

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import URL

from app.db import (
    Base,
    _engine_connect_args,
    _engine_kwargs,
    _normalize_database_url,
    _uses_transaction_pooler,
    create_db_engine,
)
from app.models import Event  # noqa: F401

HOST = "aws-1-eu-west-1.pooler.supabase.com"
USER = "postgres.kovjpgflputeexnzwizu"
# Includes /, #, ?, :, and @. The "@:/" sequence is what makes SQLAlchemy's
# own regex capture an empty port and call int('').
SPECIAL_PASSWORD = "bthK/secr#et?query:p@:/ss"


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


def _supabase_url(password: str, port: int, *, scheme: str = "postgresql") -> str:
    return (
        f"{scheme}://{USER}:{password}@{HOST}:{port}/postgres?sslmode=require"
    )


def _capture_engine_target(monkeypatch, url: str):
    captured: dict = {}
    import app.db as db

    original = db.create_engine

    def spy(target, *args, **kwargs):
        captured["target"] = target
        return original(target, *args, **kwargs)

    monkeypatch.setattr(db, "create_engine", spy)
    engine = create_db_engine(url)
    engine.dispose()
    return captured["target"]


def test_password_with_url_special_characters_keeps_real_port(monkeypatch):
    session = _normalize_database_url(_supabase_url(SPECIAL_PASSWORD, 5432))
    transaction = _normalize_database_url(
        _supabase_url(SPECIAL_PASSWORD, 6543, scheme="postgres")
    )
    assert _uses_transaction_pooler(session) is False
    assert "prepare_threshold" not in _engine_connect_args(session)
    assert _engine_kwargs(session)["pool_pre_ping"] is True
    assert _uses_transaction_pooler(transaction) is True
    assert _engine_connect_args(transaction)["prepare_threshold"] is None

    session_target = _capture_engine_target(monkeypatch, session)
    assert isinstance(session_target, URL)
    assert session_target.port == 5432
    assert session_target.host == HOST
    assert session_target.username == USER
    assert session_target.password == SPECIAL_PASSWORD
    assert session_target.database == "postgres"
    assert session_target.drivername == "postgresql+psycopg"
    assert session_target.query["sslmode"] == "require"

    transaction_target = _capture_engine_target(monkeypatch, transaction)
    assert isinstance(transaction_target, URL)
    assert transaction_target.port == 6543
    assert transaction_target.host == HOST
    assert transaction_target.password == SPECIAL_PASSWORD


def test_percent_encoded_password_keeps_real_port(monkeypatch):
    encoded = quote(SPECIAL_PASSWORD, safe="")
    url = _supabase_url(encoded, 5432)
    target = _capture_engine_target(monkeypatch, url)
    assert isinstance(target, URL)
    assert target.port == 5432
    assert target.host == HOST
    assert target.password == SPECIAL_PASSWORD
    assert "prepare_threshold" not in _engine_connect_args(_normalize_database_url(url))


def test_supabase_session_and_transaction_ports(monkeypatch):
    session = _capture_engine_target(
        monkeypatch,
        "postgresql://postgres.example:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres",
    )
    assert isinstance(session, URL)
    assert session.port == 5432
    assert session.host == HOST
    assert session.drivername == "postgresql+psycopg"
    assert "prepare_threshold" not in _engine_connect_args(
        _normalize_database_url(
            "postgresql://postgres.example:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
        )
    )

    transaction = _capture_engine_target(
        monkeypatch,
        "postgres://postgres.example:secret@aws-1-eu-west-1.pooler.supabase.com:6543/postgres",
    )
    assert isinstance(transaction, URL)
    assert transaction.port == 6543
    assert transaction.host == HOST
    normalized = _normalize_database_url(
        "postgres://postgres.example:secret@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    )
    assert _engine_connect_args(normalized)["prepare_threshold"] is None
    assert _engine_kwargs(normalized)["pool_pre_ping"] is True


def test_non_numeric_port_is_rejected():
    url = "postgresql+psycopg://user:pass@db.example:bthK/postgres"
    with pytest.raises(ValueError, match="Invalid database URL port 'bthK'"):
        _uses_transaction_pooler(url)
    with pytest.raises(ValueError, match="Invalid database URL port 'bthK'"):
        create_db_engine(url)


def test_empty_port_is_rejected_before_sqlalchemy():
    url = "postgresql+psycopg://user:pass@db.example:/postgres"
    with pytest.raises(ValueError, match="Invalid database URL port ''"):
        create_db_engine(url)


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