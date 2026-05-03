from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Channel, Contractor
from app.models.onboarding import OnboardingSession

_NIF_RE = re.compile(
    r"^(\d{8}[A-Z]|[XYZ]\d{7}[A-Z]|[ABCDEFGHJNPQRSUVW]\d{7}[A-Z0-9])$"
)
_PHONE_RE = re.compile(r"^\+\d{7,15}$")

_PROMPTS: dict[str, str] = {
    "ask_type": (
        "Hola, soy Noa. ¿Eres profesional autónomo o quieres contactar con algún profesional?"
    ),
    "ask_name": "¿Cómo te llamas?",
    "ask_business": (
        "¿Cómo se llama tu negocio o empresa? Si trabajas a tu nombre, repite tu nombre."
    ),
    "ask_phone": (
        "¿Cuál es tu número de teléfono? Incluye el prefijo internacional (ej. +34600000000)."
    ),
    "ask_nif": "¿Cuál es tu NIF, NIE o CIF?",
    "ask_iban": (
        "¿Cuál es tu IBAN para recibir pagos? Escribe 'saltar' si no lo tienes ahora."
    ),
}


def validate_nif(value: str) -> bool:
    """Return True if value is a valid Spanish NIF, NIE, or CIF."""
    normalized = value.strip().upper().replace(" ", "").replace("-", "")
    return bool(_NIF_RE.match(normalized))


async def handle_onboarding_message(
    db: AsyncSession, chat_id: str, channel: str, text: str | None
) -> str:
    row = await db.execute(
        select(OnboardingSession).where(OnboardingSession.chat_id == chat_id)
    )
    session = row.scalar_one_or_none()

    if session is None:
        session = OnboardingSession(
            chat_id=chat_id, channel=channel, step="ask_type", data={}
        )
        db.add(session)
        await db.commit()
        return _PROMPTS["ask_type"]

    text = (text or "").strip()

    if session.step == "ask_type":
        normalized = text.lower()
        # Match any affirmative or the word root "aut" (autónomo/autonomo/etc.)
        is_contractor = "aut" in normalized or normalized in (
            "si", "sí", "yes", "1", "profesional", "soy profesional"
        )
        if is_contractor:
            session.step = "ask_name"
            await db.commit()
            return _PROMPTS["ask_name"]
        return (
            "Para contactar con un profesional, pídele que te comparta este número. "
            "Si eres autónomo y quieres registrarte, escribe 'autónomo'."
        )

    if session.step == "ask_name":
        if len(text) < 2:
            return "Por favor, dime tu nombre completo."
        session.data = {**session.data, "name": text}
        session.step = "ask_business"
        await db.commit()
        return _PROMPTS["ask_business"]

    if session.step == "ask_business":
        if len(text) < 2:
            return "Por favor, dime el nombre de tu negocio."
        session.data = {**session.data, "business_name": text}
        session.step = "ask_phone"
        await db.commit()
        return _PROMPTS["ask_phone"]

    if session.step == "ask_phone":
        normalized = re.sub(r"[\s\-\(\)]", "", text)
        if not _PHONE_RE.match(normalized):
            return "Formato no válido. Por ejemplo: +34600000000"
        session.data = {**session.data, "phone": normalized}
        session.step = "ask_nif"
        await db.commit()
        return _PROMPTS["ask_nif"]

    if session.step == "ask_nif":
        normalized = text.upper().replace(" ", "").replace("-", "")
        if not validate_nif(normalized):
            return (
                "Formato no válido. Acepto:\n"
                "· NIF: 12345678A\n"
                "· NIE: X1234567L\n"
                "· CIF: B12345678\n"
                "¿Puedes revisarlo?"
            )
        session.data = {**session.data, "nif": normalized}
        session.step = "ask_iban"
        await db.commit()
        return _PROMPTS["ask_iban"]

    if session.step == "ask_iban":
        iban: str | None
        if text.lower() in ("saltar", "skip", "no", "no tengo", "sin iban"):
            iban = None
        else:
            iban = text.upper().replace(" ", "")
        contractor = await _create_contractor(db, session, iban)
        await db.delete(session)
        await db.commit()
        return (
            f"Perfecto, {contractor.name}. ¡Ya puedes empezar a usar Noa! "
            "Cuéntame qué has hecho hoy o escribe 'ayuda' para ver todo lo que puedo hacer."
        )

    return _PROMPTS["ask_type"]


async def _create_contractor(
    db: AsyncSession, session: OnboardingSession, iban: str | None
) -> Contractor:
    data: dict[str, Any] = session.data
    contractor = Contractor(
        phone_number=data["phone"],
        name=data["name"],
        business_name=data.get("business_name"),
        nif=data.get("nif"),
        iban=iban,
        channel=Channel.telegram if session.channel == "telegram" else Channel.whatsapp,
        telegram_chat_id=session.chat_id if session.channel == "telegram" else None,
        onboarded_at=datetime.now(UTC),
    )
    db.add(contractor)
    await db.flush()
    return contractor
