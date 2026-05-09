"""Unit tests for app.ai.context — build_contractor_context()."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.context import build_contractor_context


def _db(recent_clients: list[MagicMock], total: int | None = None) -> AsyncMock:
    """Mock db with scalar() returning total and execute() returning recent_clients.

    When total is omitted it defaults to len(recent_clients) — the ≤10 case.
    """
    db = AsyncMock()
    db.scalar.return_value = total if total is not None else len(recent_clients)
    result = MagicMock()
    result.scalars.return_value.all.return_value = recent_clients
    db.execute.return_value = result
    return db


def _contractor(
    *,
    name: str = "Pedro García",
    business_name: str | None = "Fontanería García",
    nif: str | None = "12345678A",
    iban: str | None = "ES91 2100 0418 4502 0005 1332",
    iva_rate: float = 0.21,
    irpf_rate: float = 0.15,
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.name = name
    c.business_name = business_name
    c.nif = nif
    c.iban = iban
    c.iva_rate = iva_rate
    c.irpf_rate = irpf_rate
    return c


def _client(name: str = "Ana López", phone: str = "+34600000001") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.name = name
    c.phone_number = phone
    return c


class TestContractorProfile:
    @pytest.mark.asyncio
    async def test_contains_name(self) -> None:
        result = await build_contractor_context(_db([]), _contractor(name="Pedro García"))
        assert "Pedro García" in result

    @pytest.mark.asyncio
    async def test_contains_business_name(self) -> None:
        cont = _contractor(business_name="Fontanería García")
        result = await build_contractor_context(_db([]), cont)
        assert "Fontanería García" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_name_when_no_business_name(self) -> None:
        cont = _contractor(name="Pedro García", business_name=None)
        result = await build_contractor_context(_db([]), cont)
        assert "Pedro García" in result

    @pytest.mark.asyncio
    async def test_contains_nif(self) -> None:
        result = await build_contractor_context(_db([]), _contractor(nif="12345678A"))
        assert "12345678A" in result

    @pytest.mark.asyncio
    async def test_omits_nif_when_none(self) -> None:
        result = await build_contractor_context(_db([]), _contractor(nif=None))
        assert "NIF" not in result

    @pytest.mark.asyncio
    async def test_contains_iban(self) -> None:
        cont = _contractor(iban="ES91 2100 0418 4502 0005 1332")
        result = await build_contractor_context(_db([]), cont)
        assert "ES91" in result

    @pytest.mark.asyncio
    async def test_omits_iban_when_none(self) -> None:
        result = await build_contractor_context(_db([]), _contractor(iban=None))
        assert "IBAN" not in result

    @pytest.mark.asyncio
    async def test_iva_rate_formatted_as_percent(self) -> None:
        result = await build_contractor_context(_db([]), _contractor(iva_rate=0.21))
        assert "21%" in result

    @pytest.mark.asyncio
    async def test_irpf_rate_formatted_as_percent(self) -> None:
        result = await build_contractor_context(_db([]), _contractor(irpf_rate=0.15))
        assert "15%" in result


class TestClientRoster:
    @pytest.mark.asyncio
    async def test_client_name_appears(self) -> None:
        result = await build_contractor_context(_db([_client(name="Ana López")]), _contractor())
        assert "Ana López" in result

    @pytest.mark.asyncio
    async def test_client_phone_appears(self) -> None:
        result = await build_contractor_context(_db([_client(phone="+34600000001")]), _contractor())
        assert "+34600000001" in result

    @pytest.mark.asyncio
    async def test_client_id_appears(self) -> None:
        client = _client()
        result = await build_contractor_context(_db([client]), _contractor())
        assert str(client.id) in result

    @pytest.mark.asyncio
    async def test_empty_client_list_placeholder(self) -> None:
        result = await build_contractor_context(_db([]), _contractor())
        assert "sin clientes" in result

    @pytest.mark.asyncio
    async def test_multiple_clients_all_appear(self) -> None:
        clients = [_client("Ana López"), _client("Juan Ruiz", "+34600000002")]
        result = await build_contractor_context(_db(clients), _contractor())
        assert "Ana López" in result
        assert "Juan Ruiz" in result

    @pytest.mark.asyncio
    async def test_client_count_in_header_under_limit(self) -> None:
        clients = [_client("A"), _client("B")]
        result = await build_contractor_context(_db(clients), _contractor())
        assert "2" in result

    # ------------------------------------------------------------------
    # Hybrid roster behaviour
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_header_shows_simple_count_when_at_or_under_limit(self) -> None:
        clients = [_client(f"Cliente {i}") for i in range(10)]
        result = await build_contractor_context(_db(clients, total=10), _contractor())
        assert "10" in result
        assert "search_client" not in result

    @pytest.mark.asyncio
    async def test_header_shows_recent_n_de_total_when_over_limit(self) -> None:
        clients = [_client(f"Cliente {i}") for i in range(10)]
        result = await build_contractor_context(_db(clients, total=25), _contractor())
        assert "10 de 25" in result

    @pytest.mark.asyncio
    async def test_search_client_hint_present_when_over_limit(self) -> None:
        clients = [_client(f"Cliente {i}") for i in range(10)]
        result = await build_contractor_context(_db(clients, total=11), _contractor())
        assert "search_client" in result

    @pytest.mark.asyncio
    async def test_search_client_hint_absent_when_under_limit(self) -> None:
        clients = [_client(f"Cliente {i}") for i in range(5)]
        result = await build_contractor_context(_db(clients, total=5), _contractor())
        assert "search_client" not in result
