import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from jose import jwt

from app.api.v1 import dependencies as deps
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Event  # noqa: F401

TEST_SUPABASE_URL = "https://test-project.supabase.co"
TEST_KID = "test-ec-signing-key-id"

# Deterministic static EC private key PEM (secp256r1) for consistent signing across all test modules
_TEST_PRIVATE_PEM = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgFokIB/WaAIZwC1uL\n"
    "CmnqlBNseeO0McWOrDPKhQsFHPKhRANCAARTmAodXDZdlpe0Oea0EBsj8wHq3NqT\n"
    "UALzjWcleWSgnremIa0b//l9FDh3wmQ2MSrx58oVF16uR2MVMxqajqRD\n"
    "-----END PRIVATE KEY-----\n"
)

_TEST_PUBLIC_JWK = {
    "kty": "EC",
    "crv": "P-256",
    "alg": "ES256",
    "use": "sig",
    "kid": TEST_KID,
    "x": "U5gKHVw2XZaXtDnmtBAbI_MB6tzak1AC841nJXlkoJ4",
    "y": "t6YhrRv_-X0UOHfCZDYxKvHnyhUXXq5HYxUzGpqOpEM",
}

TEST_JWKS = {
    "keys": [_TEST_PUBLIC_JWK]
}

settings.supabase_url = TEST_SUPABASE_URL
deps.fetch_jwks = lambda _url: TEST_JWKS


def make_test_token(
    sub: str = "test_user",
    private_key_pem: str = _TEST_PRIVATE_PEM,
    kid: str = TEST_KID,
    iss: str = f"{TEST_SUPABASE_URL}/auth/v1",
    exp: int = 9999999999,
    aud: str = "authenticated",
) -> str:
    payload = {
        "sub": sub,
        "aud": aud,
        "iss": iss,
        "role": "authenticated",
        "exp": exp,
    }
    return jwt.encode(payload, private_key_pem, algorithm="ES256", headers={"kid": kid})


def auth_headers(sub: str = "test_user") -> dict[str, str]:
    return {"Authorization": f"Bearer {make_test_token(sub)}"}


@pytest.fixture(autouse=True)
def mock_jwks_provider():
    """Automatically mock JWKS fetching across tests so real network is never touched."""
    settings.supabase_url = TEST_SUPABASE_URL
    deps.jwks_cache.clear()
    deps.fetch_jwks = lambda _url: TEST_JWKS
    yield
    settings.supabase_url = TEST_SUPABASE_URL
    deps.fetch_jwks = lambda _url: TEST_JWKS
    deps.jwks_cache.clear()


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
