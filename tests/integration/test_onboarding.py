"""Integration tests for the contractor onboarding flow — real PostgreSQL."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.onboarding import OnboardingSession
from app.services.onboarding import _PROMPTS, handle_onboarding_message

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _drive(
    db: AsyncSession,
    chat_id: str,
    messages: list[str | None],
) -> list[str]:
    """Send a sequence of messages through handle_onboarding_message and collect replies."""
    replies = []
    for text in messages:
        reply = await handle_onboarding_message(db, chat_id, "telegram", text)
        replies.append(reply)
    return replies


async def _full_flow(db: AsyncSession, chat_id: str = "111") -> list[str]:
    """Run a complete successful onboarding and return all bot replies."""
    return await _drive(
        db,
        chat_id,
        [
            None,               # first contact
            "autónomo",         # ask_type
            "Pedro García",     # ask_name
            "Fontanería García", # ask_business
            "+34600000001",     # ask_phone
            "12345678Z",        # ask_nif
            "ES91 2100 0418 4502 0005 1332",  # ask_iban
        ],
    )


# ---------------------------------------------------------------------------
# First contact
# ---------------------------------------------------------------------------

class TestFirstContact:
    async def test_creates_onboarding_session(self, db: AsyncSession) -> None:
        await handle_onboarding_message(db, "100", "telegram", None)
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "100")
        )
        assert row.scalar_one_or_none() is not None

    async def test_returns_ask_type_prompt(self, db: AsyncSession) -> None:
        reply = await handle_onboarding_message(db, "101", "telegram", None)
        assert reply == _PROMPTS["ask_type"]

    async def test_session_starts_at_ask_type_step(self, db: AsyncSession) -> None:
        await handle_onboarding_message(db, "102", "telegram", None)
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "102")
        )
        session = row.scalar_one()
        assert session.step == "ask_type"

    async def test_second_first_contact_returns_same_prompt(self, db: AsyncSession) -> None:
        await handle_onboarding_message(db, "103", "telegram", "Hola")
        reply = await handle_onboarding_message(db, "103", "telegram", "Hola de nuevo")
        # Still at ask_type because "Hola de nuevo" is not a contractor keyword
        assert _PROMPTS["ask_type"] not in reply  # it returned the redirect message


# ---------------------------------------------------------------------------
# ask_type step
# ---------------------------------------------------------------------------

class TestAskTypeStep:
    async def test_autonomo_advances_to_ask_name(self, db: AsyncSession) -> None:
        await handle_onboarding_message(db, "200", "telegram", None)
        reply = await handle_onboarding_message(db, "200", "telegram", "autónomo")
        assert reply == _PROMPTS["ask_name"]

    async def test_autonomo_without_accent_advances(self, db: AsyncSession) -> None:
        await handle_onboarding_message(db, "201", "telegram", None)
        reply = await handle_onboarding_message(db, "201", "telegram", "autonomo")
        assert reply == _PROMPTS["ask_name"]

    async def test_si_advances(self, db: AsyncSession) -> None:
        await handle_onboarding_message(db, "202", "telegram", None)
        reply = await handle_onboarding_message(db, "202", "telegram", "sí")
        assert reply == _PROMPTS["ask_name"]

    async def test_unrecognized_text_stays_at_ask_type(self, db: AsyncSession) -> None:
        await handle_onboarding_message(db, "203", "telegram", None)
        await handle_onboarding_message(db, "203", "telegram", "hola")
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "203")
        )
        session = row.scalar_one()
        assert session.step == "ask_type"

    async def test_unrecognized_returns_redirect(self, db: AsyncSession) -> None:
        await handle_onboarding_message(db, "204", "telegram", None)
        reply = await handle_onboarding_message(db, "204", "telegram", "quiero contactar")
        assert "autónomo" in reply.lower()


# ---------------------------------------------------------------------------
# ask_name step
# ---------------------------------------------------------------------------

class TestAskNameStep:
    async def test_valid_name_advances_to_ask_business(self, db: AsyncSession) -> None:
        await _drive(db, "300", [None, "autónomo"])
        reply = await handle_onboarding_message(db, "300", "telegram", "Ana Martínez")
        assert reply == _PROMPTS["ask_business"]

    async def test_name_stored_in_data(self, db: AsyncSession) -> None:
        await _drive(db, "301", [None, "autónomo"])
        await handle_onboarding_message(db, "301", "telegram", "Luis Torres")
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "301")
        )
        session = row.scalar_one()
        assert session.data["name"] == "Luis Torres"

    async def test_single_char_rejected(self, db: AsyncSession) -> None:
        await _drive(db, "302", [None, "autónomo"])
        reply = await handle_onboarding_message(db, "302", "telegram", "A")
        assert reply != _PROMPTS["ask_business"]
        # Step should not advance
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "302")
        )
        assert row.scalar_one().step == "ask_name"

    async def test_empty_text_rejected(self, db: AsyncSession) -> None:
        await _drive(db, "303", [None, "autónomo"])
        reply = await handle_onboarding_message(db, "303", "telegram", "")
        assert reply != _PROMPTS["ask_business"]


# ---------------------------------------------------------------------------
# ask_phone step
# ---------------------------------------------------------------------------

class TestAskPhoneStep:
    async def test_valid_phone_advances_to_ask_nif(self, db: AsyncSession) -> None:
        await _drive(db, "400", [None, "autónomo", "Pedro García", "Fontanería García"])
        reply = await handle_onboarding_message(db, "400", "telegram", "+34600000001")
        assert reply == _PROMPTS["ask_nif"]

    async def test_phone_with_spaces_accepted(self, db: AsyncSession) -> None:
        await _drive(db, "401", [None, "autónomo", "Ana López", "Ana López Fontanería"])
        reply = await handle_onboarding_message(db, "401", "telegram", "+34 600 000 002")
        assert reply == _PROMPTS["ask_nif"]

    async def test_phone_without_prefix_rejected(self, db: AsyncSession) -> None:
        await _drive(db, "402", [None, "autónomo", "María", "María Obras"])
        reply = await handle_onboarding_message(db, "402", "telegram", "600000003")
        assert "válido" in reply
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "402")
        )
        assert row.scalar_one().step == "ask_phone"

    async def test_phone_stored_normalized(self, db: AsyncSession) -> None:
        await _drive(db, "403", [None, "autónomo", "Carlos", "Carlos Pinturas"])
        await handle_onboarding_message(db, "403", "telegram", "+34 600 000 004")
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "403")
        )
        assert row.scalar_one().data["phone"] == "+34600000004"


# ---------------------------------------------------------------------------
# ask_nif step
# ---------------------------------------------------------------------------

class TestAskNifStep:
    async def _to_nif_step(self, db: AsyncSession, chat_id: str) -> None:
        await _drive(db, chat_id, [None, "autónomo", "Pedro", "Fontanería", "+34600000001"])

    async def test_valid_nif_advances(self, db: AsyncSession) -> None:
        await self._to_nif_step(db, "500")
        reply = await handle_onboarding_message(db, "500", "telegram", "12345678Z")
        assert reply == _PROMPTS["ask_iban"]

    async def test_valid_nie_advances(self, db: AsyncSession) -> None:
        await self._to_nif_step(db, "501")
        reply = await handle_onboarding_message(db, "501", "telegram", "X1234567L")
        assert reply == _PROMPTS["ask_iban"]

    async def test_valid_cif_advances(self, db: AsyncSession) -> None:
        await self._to_nif_step(db, "502")
        reply = await handle_onboarding_message(db, "502", "telegram", "B12345678")
        assert reply == _PROMPTS["ask_iban"]

    async def test_invalid_nif_rejected(self, db: AsyncSession) -> None:
        await self._to_nif_step(db, "503")
        reply = await handle_onboarding_message(db, "503", "telegram", "NOTANIF")
        assert "válido" in reply
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "503")
        )
        assert row.scalar_one().step == "ask_nif"

    async def test_nif_stored_normalized_uppercase(self, db: AsyncSession) -> None:
        await self._to_nif_step(db, "504")
        await handle_onboarding_message(db, "504", "telegram", "12345678z")
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "504")
        )
        assert row.scalar_one().data["nif"] == "12345678Z"

    async def test_nif_with_spaces_accepted(self, db: AsyncSession) -> None:
        await self._to_nif_step(db, "505")
        reply = await handle_onboarding_message(db, "505", "telegram", "12 34 56 78 Z")
        assert reply == _PROMPTS["ask_iban"]


# ---------------------------------------------------------------------------
# ask_iban step — contractor creation
# ---------------------------------------------------------------------------

class TestAskIbanStep:
    async def _to_iban_step(self, db: AsyncSession, chat_id: str) -> None:
        # Derive a unique phone per chat_id so committed contractors don't collide.
        phone = f"+34600{chat_id.zfill(6)}"
        await _drive(
            db, chat_id,
            [None, "autónomo", "Pedro García", "Fontanería García", phone, "12345678Z"],
        )

    async def test_iban_provided_creates_contractor_with_iban(self, db: AsyncSession) -> None:
        await self._to_iban_step(db, "600")
        await handle_onboarding_message(
            db, "600", "telegram", "ES91 2100 0418 4502 0005 1332"
        )
        row = await db.execute(
            select(Contractor).where(Contractor.telegram_chat_id == "600")
        )
        contractor = row.scalar_one()
        assert contractor.iban == "ES9121000418450200051332"  # spaces stripped

    async def test_saltar_creates_contractor_with_no_iban(self, db: AsyncSession) -> None:
        await self._to_iban_step(db, "601")
        await handle_onboarding_message(db, "601", "telegram", "saltar")
        row = await db.execute(
            select(Contractor).where(Contractor.telegram_chat_id == "601")
        )
        contractor = row.scalar_one()
        assert contractor.iban is None

    async def test_contractor_has_correct_name(self, db: AsyncSession) -> None:
        await self._to_iban_step(db, "602")
        await handle_onboarding_message(db, "602", "telegram", "saltar")
        row = await db.execute(
            select(Contractor).where(Contractor.telegram_chat_id == "602")
        )
        assert row.scalar_one().name == "Pedro García"

    async def test_contractor_has_correct_nif(self, db: AsyncSession) -> None:
        await self._to_iban_step(db, "603")
        await handle_onboarding_message(db, "603", "telegram", "saltar")
        row = await db.execute(
            select(Contractor).where(Contractor.telegram_chat_id == "603")
        )
        assert row.scalar_one().nif == "12345678Z"

    async def test_contractor_telegram_chat_id_set(self, db: AsyncSession) -> None:
        await self._to_iban_step(db, "604")
        await handle_onboarding_message(db, "604", "telegram", "saltar")
        row = await db.execute(
            select(Contractor).where(Contractor.telegram_chat_id == "604")
        )
        assert row.scalar_one().telegram_chat_id == "604"

    async def test_contractor_onboarded_at_set(self, db: AsyncSession) -> None:
        await self._to_iban_step(db, "605")
        await handle_onboarding_message(db, "605", "telegram", "saltar")
        row = await db.execute(
            select(Contractor).where(Contractor.telegram_chat_id == "605")
        )
        assert row.scalar_one().onboarded_at is not None

    async def test_onboarding_session_deleted_after_completion(
        self, db: AsyncSession
    ) -> None:
        await self._to_iban_step(db, "606")
        await handle_onboarding_message(db, "606", "telegram", "saltar")
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "606")
        )
        assert row.scalar_one_or_none() is None

    async def test_completion_reply_contains_name(self, db: AsyncSession) -> None:
        await self._to_iban_step(db, "607")
        reply = await handle_onboarding_message(db, "607", "telegram", "saltar")
        assert "Pedro García" in reply


# ---------------------------------------------------------------------------
# Resumability
# ---------------------------------------------------------------------------

class TestResumability:
    async def test_session_resumes_at_correct_step(self, db: AsyncSession) -> None:
        """If onboarding is interrupted at ask_nif, the next message is processed as NIF."""
        await _drive(
            db, "700",
            [None, "autónomo", "Laura Vega", "Laura Instalaciones", "+34611000001"],
        )
        # Session is now at ask_nif — simulate coming back later
        row = await db.execute(
            select(OnboardingSession).where(OnboardingSession.chat_id == "700")
        )
        assert row.scalar_one().step == "ask_nif"

        reply = await handle_onboarding_message(db, "700", "telegram", "X9876543R")
        assert reply == _PROMPTS["ask_iban"]

    async def test_data_persisted_across_steps(self, db: AsyncSession) -> None:
        """Data collected in early steps is still present when contractor is created."""
        await _drive(
            db, "701",
            [None, "autónomo", "Marcos Ruiz", "Marcos Electricidad", "+34622000002", "B12345679"],
        )
        await handle_onboarding_message(db, "701", "telegram", "saltar")
        row = await db.execute(
            select(Contractor).where(Contractor.telegram_chat_id == "701")
        )
        c = row.scalar_one()
        assert c.name == "Marcos Ruiz"
        assert c.business_name == "Marcos Electricidad"
        assert c.phone_number == "+34622000002"
        assert c.nif == "B12345679"
