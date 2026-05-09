"""Integration tests for /auth/google/connect and /auth/google/callback."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.appointment import CalendarProviderEnum, CalendarToken
from tests.integration.conftest import make_contractor


async def _make_pending_token(db: AsyncSession, contractor_id: object) -> CalendarToken:
    token = CalendarToken(
        contractor_id=contractor_id,  # type: ignore[arg-type]
        provider=CalendarProviderEnum.google,
        state=str(uuid.uuid4()),
        access_token=None,
        refresh_token=None,
    )
    db.add(token)
    await db.flush()
    return token


@pytest.fixture
def http_client(db: AsyncSession):  # type: ignore[misc]
    """AsyncClient wired to the FastAPI app, sharing the test DB session."""

    async def _override_db():
        yield db

    from app.database import get_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    client = AsyncClient(transport=transport, base_url="http://test")
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /auth/google/connect
# ---------------------------------------------------------------------------


def _mock_flow(auth_url: str = "https://accounts.google.com/o/oauth2/auth?fake=1") -> MagicMock:
    mock = MagicMock()
    mock.authorization_url.return_value = (auth_url, "state")
    return mock


class TestGoogleConnect:
    async def test_redirects_to_google(
        self, http_client: AsyncClient, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        token = await _make_pending_token(db, contractor.id)

        with patch("app.api.calendar_auth._make_flow", return_value=_mock_flow()):
            resp = await http_client.get(
                f"/auth/google/connect?state={token.state}", follow_redirects=False
            )

        assert resp.status_code == 307
        assert "accounts.google.com" in resp.headers["location"]

    async def test_pkce_challenge_passed_to_authorization_url(
        self, http_client: AsyncClient, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        token = await _make_pending_token(db, contractor.id)
        mock_flow = _mock_flow()

        with patch("app.api.calendar_auth._make_flow", return_value=mock_flow):
            await http_client.get(
                f"/auth/google/connect?state={token.state}", follow_redirects=False
            )

        _, kwargs = mock_flow.authorization_url.call_args
        assert kwargs.get("code_challenge_method") == "S256"
        assert kwargs.get("code_challenge") is not None

    async def test_code_verifier_persisted(
        self, http_client: AsyncClient, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        token = await _make_pending_token(db, contractor.id)

        with patch("app.api.calendar_auth._make_flow", return_value=_mock_flow()):
            await http_client.get(
                f"/auth/google/connect?state={token.state}", follow_redirects=False
            )

        await db.refresh(token)
        assert token.code_verifier is not None
        assert len(token.code_verifier) >= 43

    async def test_invalid_state_returns_400(
        self, http_client: AsyncClient, db: AsyncSession
    ) -> None:
        resp = await http_client.get(
            "/auth/google/connect?state=nonexistent", follow_redirects=False
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /auth/google/callback
# ---------------------------------------------------------------------------


class TestGoogleCallback:
    async def test_callback_passes_code_verifier_to_fetch_token(
        self, http_client: AsyncClient, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        token = await _make_pending_token(db, contractor.id)
        token.code_verifier = "test-verifier-abc123"
        await db.flush()

        fake_creds = MagicMock()
        fake_creds.token = "access-tok"
        fake_creds.refresh_token = "refresh-tok"
        fake_creds.expiry = None

        captured: dict[str, object] = {}

        def fake_fetch_token(**kwargs: object) -> None:
            captured.update(kwargs)

        with patch("app.api.calendar_auth._make_flow") as mock_make_flow:
            mock_flow = MagicMock()
            mock_flow.fetch_token.side_effect = fake_fetch_token
            mock_flow.credentials = fake_creds
            mock_make_flow.return_value = mock_flow

            resp = await http_client.get(
                f"/auth/google/callback?code=authcode&state={token.state}"
            )

        assert resp.status_code == 200
        assert captured.get("code_verifier") == "test-verifier-abc123"

    async def test_callback_stores_tokens(
        self, http_client: AsyncClient, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        token = await _make_pending_token(db, contractor.id)
        token.code_verifier = "some-verifier"
        await db.flush()

        fake_creds = MagicMock()
        fake_creds.token = "stored-access"
        fake_creds.refresh_token = "stored-refresh"
        fake_creds.expiry = None

        with patch("app.api.calendar_auth._make_flow") as mock_make_flow:
            mock_flow = MagicMock()
            mock_flow.credentials = fake_creds
            mock_make_flow.return_value = mock_flow

            resp = await http_client.get(
                f"/auth/google/callback?code=authcode&state={token.state}"
            )

        assert resp.status_code == 200
        await db.refresh(token)
        assert token.access_token == "stored-access"
        assert token.refresh_token == "stored-refresh"

    async def test_callback_invalid_state_returns_400(
        self, http_client: AsyncClient, db: AsyncSession
    ) -> None:
        resp = await http_client.get(
            "/auth/google/callback?code=authcode&state=nonexistent"
        )
        assert resp.status_code == 400

    async def test_callback_token_exchange_failure_returns_400(
        self, http_client: AsyncClient, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        token = await _make_pending_token(db, contractor.id)
        token.code_verifier = "some-verifier"
        await db.flush()

        with patch("app.api.calendar_auth._make_flow") as mock_make_flow:
            mock_flow = MagicMock()
            mock_flow.fetch_token.side_effect = Exception(
                "(invalid_grant) Missing code verifier."
            )
            mock_make_flow.return_value = mock_flow

            resp = await http_client.get(
                f"/auth/google/callback?code=authcode&state={token.state}"
            )

        assert resp.status_code == 400
