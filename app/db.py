from collections.abc import Generator
from pathlib import Path
from urllib.parse import parse_qsl, unquote

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_directory(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw_path = url.removeprefix("sqlite:///")
    if raw_path in {":memory:", ""}:
        return
    path = Path(raw_path)
    if path.parent.as_posix() not in {".", ""}:
        path.parent.mkdir(parents=True, exist_ok=True)


def _normalize_database_url(url: str) -> str:
    """Use psycopg for plain PostgreSQL URLs. Leave explicit dialects and SQLite alone."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _uses_psycopg3(url: str) -> bool:
    return url.startswith("postgresql+psycopg://")


def _scheme_and_remainder(url: str) -> tuple[str, str]:
    if "://" not in url:
        raise ValueError("Invalid database URL: missing scheme.")
    scheme, remainder = url.split("://", 1)
    return scheme, remainder


def _parse_port_text(port_text: str) -> int:
    port_text = port_text.strip()
    if not port_text.isascii() or not port_text.isdigit():
        raise ValueError(
            f"Invalid database URL port {port_text!r}. Expected a numeric port."
        )
    port = int(port_text)
    if not 0 <= port <= 65535:
        raise ValueError(
            f"Invalid database URL port {port!r}. Port must be between 0 and 65535."
        )
    return port


def _split_host_port(hostport: str) -> tuple[str, int | None]:
    if not hostport:
        raise ValueError("Invalid database URL: missing host.")
    if hostport.startswith("["):
        bracket_end = hostport.find("]")
        if bracket_end == -1:
            raise ValueError("Invalid database URL: unclosed IPv6 host.")
        host = hostport[1:bracket_end]
        port_section = hostport[bracket_end + 1 :]
        if not port_section:
            return host, None
        if not port_section.startswith(":"):
            raise ValueError("Invalid database URL: malformed IPv6 host.")
        return host, _parse_port_text(port_section[1:])
    if ":" not in hostport:
        return hostport, None
    if hostport.count(":") > 1:
        raise ValueError("Invalid database URL: malformed host.")
    host, port_text = hostport.split(":", 1)
    if not host:
        raise ValueError("Invalid database URL: missing host.")
    return host, _parse_port_text(port_text)


def _authority_hostport(url: str) -> str:
    """Host and port after the last ``@``.

    ``urllib.parse.urlparse().port`` raises ``ValueError`` when an unencoded
    password contains ``/``, ``?``, or ``#``, because those characters end the
    authority and the following password text is parsed as the port. The host
    is the section after the last ``@``, before the path, query, or fragment.
    """
    _, remainder = _scheme_and_remainder(url)
    hostport = remainder.rsplit("@", 1)[-1]
    cut = len(hostport)
    for separator in "/?#":
        index = hostport.find(separator)
        if index != -1:
            cut = min(cut, index)
    return hostport[:cut].strip()


def _authority_port(url: str) -> int | None:
    """Return the host port from a database URL.

    A non-numeric port is rejected here instead of being treated as a usable URL.
    """
    _, port = _split_host_port(_authority_hostport(url))
    return port


def _uses_transaction_pooler(url: str) -> bool:
    """Supabase's transaction pooler listens on 6543 and rejects prepared statements."""
    return _authority_port(url) == 6543


def _split_userinfo(userinfo: str) -> tuple[str | None, str | None]:
    if userinfo == "":
        return None, None
    if ":" not in userinfo:
        return unquote(userinfo), None
    username, password = userinfo.split(":", 1)
    return unquote(username), unquote(password)


def _parse_query(query_string: str) -> dict[str, str | list[str]]:
    query: dict[str, str | list[str]] = {}
    for key, value in parse_qsl(query_string):
        existing = query.get(key)
        if existing is None:
            query[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            query[key] = [existing, value]
    return query


def _to_sqlalchemy_url(url: str) -> URL:
    """Split a PostgreSQL URL without using SQLAlchemy's string parser.

    SQLAlchemy stops the password at the first ``@`` and treats the next colon
    as the port. A password containing ``@:/`` therefore arrives as port ``''``,
    and ``int('')`` crashes startup even when the host after the last ``@`` is
    ``:5432``. Components are taken from that last ``@`` so the original port
    and credentials are what ``create_engine`` receives.
    """
    scheme, remainder = _scheme_and_remainder(url)
    if "@" in remainder:
        userinfo, after_at = remainder.rsplit("@", 1)
    else:
        userinfo, after_at = "", remainder
    username, password = _split_userinfo(userinfo)

    fragment_at = after_at.find("#")
    if fragment_at != -1:
        after_at = after_at[:fragment_at]
    query = None
    query_at = after_at.find("?")
    if query_at != -1:
        query = _parse_query(after_at[query_at + 1 :])
        after_at = after_at[:query_at]
    database = None
    slash_at = after_at.find("/")
    if slash_at != -1:
        database = unquote(after_at[slash_at + 1 :])
        after_at = after_at[:slash_at]
    host, port = _split_host_port(after_at.strip())
    return URL.create(
        drivername=scheme,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=query,
    )


def _engine_connect_args(database_url: str) -> dict:
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        return connect_args
    if _uses_psycopg3(database_url) and _uses_transaction_pooler(database_url):
        connect_args["prepare_threshold"] = None
    return connect_args


def _engine_kwargs(database_url: str) -> dict:
    engine_kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        if ":memory:" in database_url:
            from sqlalchemy.pool import StaticPool

            engine_kwargs["poolclass"] = StaticPool
        return engine_kwargs
    if database_url.startswith("postgresql"):
        engine_kwargs["pool_pre_ping"] = True
    return engine_kwargs


def create_db_engine(url: str | None = None) -> Engine:
    database_url = _normalize_database_url(url or settings.database_url)
    _ensure_sqlite_directory(database_url)
    target: str | URL = database_url
    if database_url.startswith("postgresql"):
        target = _to_sqlalchemy_url(database_url)
    return create_engine(
        target,
        connect_args=_engine_connect_args(database_url),
        **_engine_kwargs(database_url),
    )


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
