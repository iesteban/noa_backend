"""Unit tests for app.ai.handlers.jobs — search_client and log_job."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.ai.handlers.jobs import handle_log_job, handle_search_client
from app.models.job import JobStatus
from app.models.session import UserType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session(contractor_id: uuid.UUID | None = None) -> MagicMock:
    s = MagicMock()
    s.contractor_id = contractor_id or uuid.uuid4()
    s.user_type = UserType.contractor
    return s


def _client(name: str = "Ana López", contractor_id: uuid.UUID | None = None) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.name = name
    c.phone_number = "+34600000001"
    c.contractor_id = contractor_id or uuid.uuid4()
    return c


def _db_with_clients(clients: list[MagicMock]) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = clients
    db.execute.return_value = result
    return db


def _db_with_client_get(client: MagicMock | None) -> AsyncMock:
    db = AsyncMock()
    db.get = AsyncMock(return_value=client)
    db.add = MagicMock()  # add() is synchronous in SQLAlchemy
    return db


# ---------------------------------------------------------------------------
# search_client
# ---------------------------------------------------------------------------

class TestSearchClient:
    async def test_returns_matches(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client("Pedro Mejuto", contractor_id)
        db = _db_with_clients([client])
        session = _session(contractor_id)

        result = await handle_search_client({"query": "Pedro"}, db, session)

        assert "Pedro Mejuto" in result
        assert str(client.id) in result

    async def test_returns_phone(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client("Ana López", contractor_id)
        client.phone_number = "+34611222333"
        db = _db_with_clients([client])
        session = _session(contractor_id)

        result = await handle_search_client({"query": "Ana"}, db, session)

        assert "+34611222333" in result

    async def test_no_match_returns_not_found_message(self) -> None:
        db = _db_with_clients([])
        result = await handle_search_client({"query": "Fantasma"}, db, _session())
        assert "No clients found" in result
        assert "Fantasma" in result

    async def test_empty_query_returns_error(self) -> None:
        db = _db_with_clients([])
        result = await handle_search_client({"query": ""}, db, _session())
        assert "required" in result.lower()

    async def test_missing_query_returns_error(self) -> None:
        db = _db_with_clients([])
        result = await handle_search_client({}, db, _session())
        assert "required" in result.lower()

    async def test_multiple_matches_all_listed(self) -> None:
        contractor_id = uuid.uuid4()
        clients = [_client("Pedro Alonso", contractor_id), _client("Pedro Ruiz", contractor_id)]
        db = _db_with_clients(clients)
        session = _session(contractor_id)

        result = await handle_search_client({"query": "Pedro"}, db, session)

        assert "Pedro Alonso" in result
        assert "Pedro Ruiz" in result

    async def test_count_in_result(self) -> None:
        contractor_id = uuid.uuid4()
        clients = [_client("A", contractor_id), _client("B", contractor_id)]
        db = _db_with_clients(clients)

        result = await handle_search_client({"query": "x"}, db, _session(contractor_id))

        assert "2" in result

    async def test_none_contractor_id_returns_error(self) -> None:
        session = _session()
        session.contractor_id = None
        db = _db_with_clients([])

        result = await handle_search_client({"query": "Pedro"}, db, session)

        assert "Session error" in result

    async def test_db_queried_with_contractor_scope(self) -> None:
        """execute() is called once (so the WHERE clause runs)."""
        db = _db_with_clients([])
        session = _session()

        await handle_search_client({"query": "X"}, db, session)

        db.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# log_job
# ---------------------------------------------------------------------------

class TestLogJob:
    def _valid_input(self, client_id: uuid.UUID | None = None) -> dict:  # type: ignore[type-arg]
        return {
            "client_id": str(client_id or uuid.uuid4()),
            "description": "Cambio de grifo",
            "date": "2025-06-15",
            "amount": 80.0,
        }

    async def test_happy_path_returns_confirmation(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client("Pedro Mejuto", contractor_id)
        db = _db_with_client_get(client)
        session = _session(contractor_id)

        result = await handle_log_job(self._valid_input(client.id), db, session)

        assert "Trabajo guardado" in result
        assert "Pedro Mejuto" in result
        assert "80.00€" in result

    async def test_job_added_to_session(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client("Ana López", contractor_id)
        db = _db_with_client_get(client)
        session = _session(contractor_id)

        await handle_log_job(self._valid_input(client.id), db, session)

        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert added.description == "Cambio de grifo"
        assert float(added.amount) == 80.0
        assert added.status == JobStatus.draft

    async def test_job_flushed_not_committed(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        session = _session(contractor_id)

        await handle_log_job(self._valid_input(client.id), db, session)

        db.flush.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_duration_included_when_provided(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        session = _session(contractor_id)
        inp = {**self._valid_input(client.id), "duration_hours": 2.5}

        result = await handle_log_job(inp, db, session)

        assert "2.5h" in result
        added = db.add.call_args[0][0]
        assert float(added.duration_hours) == 2.5

    async def test_duration_optional(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        session = _session(contractor_id)

        result = await handle_log_job(self._valid_input(client.id), db, session)

        assert "Duración" not in result
        added = db.add.call_args[0][0]
        assert added.duration_hours is None

    async def test_contractor_id_set_from_session(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        session = _session(contractor_id)

        await handle_log_job(self._valid_input(client.id), db, session)

        added = db.add.call_args[0][0]
        assert added.contractor_id == contractor_id

    async def test_invalid_client_uuid_returns_error(self) -> None:
        db = _db_with_client_get(None)
        inp = {**self._valid_input(), "client_id": "not-a-uuid"}

        result = await handle_log_job(inp, db, _session())

        assert "Invalid client_id" in result
        db.add.assert_not_called()

    async def test_client_from_different_contractor_returns_error(self) -> None:
        client = _client(contractor_id=uuid.uuid4())  # belongs to someone else
        db = _db_with_client_get(client)
        session = _session(uuid.uuid4())  # different contractor

        result = await handle_log_job(self._valid_input(client.id), db, session)

        assert "not found" in result.lower()
        db.add.assert_not_called()

    async def test_client_not_in_db_returns_error(self) -> None:
        db = _db_with_client_get(None)

        result = await handle_log_job(self._valid_input(), db, _session())

        assert "not found" in result.lower()
        db.add.assert_not_called()

    async def test_invalid_date_returns_error(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        inp = {**self._valid_input(client.id), "date": "15-06-2025"}

        result = await handle_log_job(inp, db, _session(contractor_id))

        assert "Invalid date" in result
        db.add.assert_not_called()

    async def test_invalid_amount_returns_error(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        inp = {**self._valid_input(client.id), "amount": "not-a-number"}

        result = await handle_log_job(inp, db, _session(contractor_id))

        assert "Invalid amount" in result
        db.add.assert_not_called()

    async def test_invalid_duration_returns_error(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        inp = {**self._valid_input(client.id), "duration_hours": "dos"}

        result = await handle_log_job(inp, db, _session(contractor_id))

        assert "Invalid duration" in result
        db.add.assert_not_called()

    async def test_missing_description_returns_error(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        inp = {**self._valid_input(client.id), "description": ""}

        result = await handle_log_job(inp, db, _session(contractor_id))

        assert "required" in result.lower()

    async def test_none_contractor_id_returns_error(self) -> None:
        db = _db_with_client_get(None)
        session = _session()
        session.contractor_id = None

        result = await handle_log_job(self._valid_input(), db, session)

        assert "Session error" in result

    async def test_result_contains_date(self) -> None:
        contractor_id = uuid.uuid4()
        client = _client(contractor_id=contractor_id)
        db = _db_with_client_get(client)
        session = _session(contractor_id)

        result = await handle_log_job(self._valid_input(client.id), db, session)

        assert "2025-06-15" in result
