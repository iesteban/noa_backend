"""Unit tests for app.services.routing — resolve_routing()."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.session import UserType
from app.services.routing import resolve_routing

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scalar_result(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_result(values: list[object]) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


def _contractor(
    telegram_chat_id: str | None = None,
    phone_number: str = "+34600000001",
    business_name: str = "Fontanería García",
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.telegram_chat_id = telegram_chat_id
    c.phone_number = phone_number
    c.business_name = business_name
    c.name = "García"
    return c


def _client(contractor_id: uuid.UUID, phone_number: str = "+34600000002") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.contractor_id = contractor_id
    c.phone_number = phone_number
    return c


# ---------------------------------------------------------------------------
# Contractor routing via telegram_chat_id
# ---------------------------------------------------------------------------

class TestContractorByTelegramChatId:
    @pytest.mark.asyncio
    async def test_returns_contractor_mode(self) -> None:
        db = AsyncMock()
        cont = _contractor(telegram_chat_id="111")
        db.execute.return_value = _scalar_result(cont)

        result = await resolve_routing(db, telegram_chat_id=111)

        assert result.user_type == UserType.contractor
        assert result.contractor_id == cont.id
        assert result.client_id is None
        assert result.candidates == []

    @pytest.mark.asyncio
    async def test_only_one_db_call_when_found(self) -> None:
        db = AsyncMock()
        db.execute.return_value = _scalar_result(_contractor(telegram_chat_id="111"))

        await resolve_routing(db, telegram_chat_id=111)

        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Contractor routing via phone_number (WhatsApp / contact share)
# ---------------------------------------------------------------------------

class TestContractorByPhoneNumber:
    @pytest.mark.asyncio
    async def test_returns_contractor_mode(self) -> None:
        db = AsyncMock()
        cont = _contractor(phone_number="+34600000001")
        db.execute.side_effect = [
            _scalar_result(None),   # telegram_chat_id lookup → miss
            _scalar_result(cont),   # phone_number → contractor hit
        ]

        result = await resolve_routing(db, telegram_chat_id=999, phone_number="+34600000001")

        assert result.user_type == UserType.contractor
        assert result.contractor_id == cont.id

    @pytest.mark.asyncio
    async def test_contractor_id_matches(self) -> None:
        db = AsyncMock()
        cont = _contractor(phone_number="+34600000001")
        db.execute.side_effect = [
            _scalar_result(None),
            _scalar_result(cont),
        ]

        result = await resolve_routing(db, telegram_chat_id=999, phone_number="+34600000001")

        assert result.contractor_id == cont.id


# ---------------------------------------------------------------------------
# Client routing
# ---------------------------------------------------------------------------

class TestClientRouting:
    @pytest.mark.asyncio
    async def test_single_client_returns_client_mode(self) -> None:
        db = AsyncMock()
        cid = uuid.uuid4()
        client = _client(contractor_id=cid)
        db.execute.side_effect = [
            _scalar_result(None),           # telegram_chat_id
            _scalar_result(None),           # phone_number → contractor
            _scalars_result([client]),      # phone_number → client
        ]

        result = await resolve_routing(db, telegram_chat_id=999, phone_number="+34600000002")

        assert result.user_type == UserType.client
        assert result.contractor_id == cid
        assert result.client_id == client.id
        assert result.candidates == []

    @pytest.mark.asyncio
    async def test_client_id_set(self) -> None:
        db = AsyncMock()
        cid = uuid.uuid4()
        client = _client(contractor_id=cid)
        db.execute.side_effect = [
            _scalar_result(None),
            _scalar_result(None),
            _scalars_result([client]),
        ]

        result = await resolve_routing(db, telegram_chat_id=999, phone_number="+34600000002")

        assert result.client_id == client.id


# ---------------------------------------------------------------------------
# Disambiguation
# ---------------------------------------------------------------------------

class TestDisambiguation:
    @pytest.mark.asyncio
    async def test_multiple_clients_returns_candidates(self) -> None:
        db = AsyncMock()
        cid1, cid2 = uuid.uuid4(), uuid.uuid4()
        client1 = _client(contractor_id=cid1, phone_number="+34600000003")
        client2 = _client(contractor_id=cid2, phone_number="+34600000003")
        cont1 = _contractor(business_name="Fontanería García")
        cont1.id = cid1
        cont2 = _contractor(business_name="Electricista Ruiz")
        cont2.id = cid2

        db.execute.side_effect = [
            _scalar_result(None),
            _scalar_result(None),
            _scalars_result([client1, client2]),
            _scalars_result([cont1, cont2]),
        ]

        result = await resolve_routing(db, telegram_chat_id=999, phone_number="+34600000003")

        assert result.user_type is None
        assert result.contractor_id is None
        assert result.client_id is None
        assert len(result.candidates) == 2

    @pytest.mark.asyncio
    async def test_candidate_names_from_business_name(self) -> None:
        db = AsyncMock()
        cid1, cid2 = uuid.uuid4(), uuid.uuid4()
        client1 = _client(contractor_id=cid1, phone_number="+34600000003")
        client2 = _client(contractor_id=cid2, phone_number="+34600000003")
        cont1 = _contractor(business_name="Fontanería García")
        cont1.id = cid1
        cont2 = _contractor(business_name="Electricista Ruiz")
        cont2.id = cid2

        db.execute.side_effect = [
            _scalar_result(None),
            _scalar_result(None),
            _scalars_result([client1, client2]),
            _scalars_result([cont1, cont2]),
        ]

        result = await resolve_routing(db, telegram_chat_id=999, phone_number="+34600000003")

        names = [name for _, name in result.candidates]
        assert "Fontanería García" in names
        assert "Electricista Ruiz" in names

    @pytest.mark.asyncio
    async def test_falls_back_to_name_when_no_business_name(self) -> None:
        db = AsyncMock()
        cid1, cid2 = uuid.uuid4(), uuid.uuid4()
        client1 = _client(contractor_id=cid1, phone_number="+34600000004")
        client2 = _client(contractor_id=cid2, phone_number="+34600000004")
        cont1 = MagicMock()
        cont1.id = cid1
        cont1.business_name = None
        cont1.name = "Pedro García"
        cont2 = MagicMock()
        cont2.id = cid2
        cont2.business_name = None
        cont2.name = "Juan Ruiz"

        db.execute.side_effect = [
            _scalar_result(None),
            _scalar_result(None),
            _scalars_result([client1, client2]),
            _scalars_result([cont1, cont2]),
        ]

        result = await resolve_routing(db, telegram_chat_id=999, phone_number="+34600000004")

        names = [name for _, name in result.candidates]
        assert "Pedro García" in names
        assert "Juan Ruiz" in names


# ---------------------------------------------------------------------------
# Unknown user
# ---------------------------------------------------------------------------

class TestUnknownUser:
    @pytest.mark.asyncio
    async def test_no_match_returns_none_user_type(self) -> None:
        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        result = await resolve_routing(db, telegram_chat_id=999)

        assert result.user_type is None

    @pytest.mark.asyncio
    async def test_no_match_empty_candidates(self) -> None:
        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        result = await resolve_routing(db, telegram_chat_id=999)

        assert result.candidates == []

    @pytest.mark.asyncio
    async def test_no_phone_number_only_one_db_call(self) -> None:
        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        await resolve_routing(db, telegram_chat_id=999, phone_number=None)

        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_phone_number_with_no_matches_unknown(self) -> None:
        db = AsyncMock()
        db.execute.side_effect = [
            _scalar_result(None),       # telegram_chat_id
            _scalar_result(None),       # phone → contractor
            _scalars_result([]),        # phone → clients
        ]

        result = await resolve_routing(db, telegram_chat_id=999, phone_number="+34699999999")

        assert result.user_type is None
        assert result.candidates == []
