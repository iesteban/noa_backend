"""Unit tests for app.ai.handlers.contractor.handle_update_contractor."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.ai.handlers.contractor import handle_update_contractor
from app.models.session import UserType


def _session(contractor_id: uuid.UUID | None = None) -> MagicMock:
    s = MagicMock()
    s.contractor_id = contractor_id or uuid.uuid4()
    s.user_type = UserType.contractor
    return s


def _contractor(**overrides: object) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.name = "Pedro García"
    c.business_name = "Fontanería García"
    c.nif = None
    c.address = None
    c.iban = None
    c.email = None
    c.iva_rate = 0.21
    c.irpf_rate = 0.15
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


def _db_with_contractor(contractor: MagicMock | None) -> AsyncMock:
    db = AsyncMock()
    db.get = AsyncMock(return_value=contractor)
    return db


class TestNoChanges:
    async def test_empty_input_returns_helpful_error(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({}, db, session)

        assert "ningún campo" in result.lower()
        db.flush.assert_not_awaited()


class TestSessionGuard:
    async def test_missing_contractor_id_returns_error(self) -> None:
        db = _db_with_contractor(_contractor())
        session = _session()
        session.contractor_id = None

        result = await handle_update_contractor({"name": "Nuevo"}, db, session)

        assert "session error" in result.lower()

    async def test_contractor_not_found_returns_error(self) -> None:
        db = _db_with_contractor(None)
        result = await handle_update_contractor({"name": "Nuevo"}, db, _session())
        assert "no encontrado" in result.lower()


class TestTextFields:
    async def test_updates_name(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor(
            {"name": "Nuevo Nombre"}, db, session
        )

        assert contractor.name == "Nuevo Nombre"
        assert "Nuevo Nombre" in result
        db.flush.assert_awaited_once()

    async def test_updates_business_name(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor(
            {"business_name": "Pedro García SL"}, db, session
        )

        assert contractor.business_name == "Pedro García SL"

    async def test_updates_address(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor(
            {"address": "Calle Mayor 1, Madrid"}, db, session
        )

        assert contractor.address == "Calle Mayor 1, Madrid"

    async def test_trims_whitespace(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor({"name": "  Pedro  "}, db, session)

        assert contractor.name == "Pedro"

    async def test_empty_string_treated_as_clear(self) -> None:
        contractor = _contractor(business_name="Old")
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor({"business_name": ""}, db, session)

        assert contractor.business_name is None

    async def test_name_cannot_be_cleared(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"name": ""}, db, session)

        assert "obligatorio" in result.lower()
        assert contractor.name == "Pedro García"  # unchanged
        db.flush.assert_not_awaited()

    async def test_address_too_long_returns_error(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor(
            {"address": "x" * 501}, db, session
        )

        assert "demasiado largo" in result.lower()
        db.flush.assert_not_awaited()


class TestNif:
    async def test_valid_nif_normalised(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        # 12345678Z is the valid DNI checksum for 12345678 (8 % 23 → "Z" letter).
        await handle_update_contractor({"nif": "12345678z"}, db, session)

        assert contractor.nif == "12345678Z"

    async def test_invalid_nif_returns_error(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"nif": "garbage"}, db, session)

        assert "no válido" in result.lower()
        db.flush.assert_not_awaited()


class TestIban:
    async def test_valid_iban_normalised(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor(
            {"iban": "es91 2100 0418 4502 0005 1332"}, db, session
        )

        assert contractor.iban == "ES9121000418450200051332"

    async def test_invalid_iban_returns_error(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"iban": "not-an-iban"}, db, session)

        assert "iban no válido" in result.lower()
        db.flush.assert_not_awaited()


class TestEmail:
    async def test_valid_email_accepted(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor(
            {"email": "Pedro@Example.Com"}, db, session
        )

        # We do not lower-case the local part.
        assert contractor.email == "Pedro@Example.Com"

    async def test_invalid_email_returns_error(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"email": "not-an-email"}, db, session)

        assert "no válido" in result.lower()
        db.flush.assert_not_awaited()


class TestRates:
    async def test_iva_rate_as_fraction(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor({"iva_rate": 0.10}, db, session)

        assert contractor.iva_rate == 0.10

    async def test_iva_rate_as_percentage_number(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor({"iva_rate": 10}, db, session)

        assert contractor.iva_rate == 0.10

    async def test_iva_rate_as_percentage_string(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor({"iva_rate": "21%"}, db, session)

        assert contractor.iva_rate == 0.21

    async def test_irpf_rate_updated(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        await handle_update_contractor({"irpf_rate": 0.07}, db, session)

        assert contractor.irpf_rate == 0.07

    async def test_invalid_rate_returns_error(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor(
            {"iva_rate": "not-a-number"}, db, session
        )

        assert "no es un número válido" in result.lower()
        db.flush.assert_not_awaited()

    async def test_rate_out_of_range_returns_error(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"iva_rate": 150}, db, session)

        assert "entre" in result.lower()
        db.flush.assert_not_awaited()

    async def test_rate_cannot_be_null(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"iva_rate": None}, db, session)

        assert "nulo" in result.lower()

    async def test_rate_bool_rejected(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"iva_rate": True}, db, session)

        assert "no es un número válido" in result.lower()


class TestMultipleFields:
    async def test_updates_several_fields_atomically(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor(
            {
                "business_name": "Pedro García SL",
                "iva_rate": 0.10,
                "iban": "ES91 2100 0418 4502 0005 1332",
            },
            db,
            session,
        )

        assert contractor.business_name == "Pedro García SL"
        assert contractor.iva_rate == 0.10
        assert contractor.iban == "ES9121000418450200051332"
        assert "Pedro García SL" in result
        assert "IBAN" in result
        assert "IVA" in result
        # Single flush — atomicity through the SQLAlchemy session.
        db.flush.assert_awaited_once()

    async def test_validation_failure_blocks_all_changes(self) -> None:
        """If any field is invalid, no field is applied."""
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor(
            {"business_name": "Valid Name", "iban": "totally-bogus"},
            db,
            session,
        )

        assert "iban no válido" in result.lower()
        assert contractor.business_name == "Fontanería García"  # unchanged
        db.flush.assert_not_awaited()


class TestSummary:
    async def test_summary_formats_rate_as_percent(self) -> None:
        contractor = _contractor()
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"iva_rate": 0.10}, db, session)

        assert "10%" in result

    async def test_summary_marks_cleared_fields(self) -> None:
        contractor = _contractor(iban="ES9121000418450200051332")
        db = _db_with_contractor(contractor)
        session = _session(contractor.id)

        result = await handle_update_contractor({"iban": ""}, db, session)

        assert "sin definir" in result.lower()
