"""Regression guards for prompt and tool-description content.

These tests don't call Claude — they verify that the strings Claude sees
contain the instructions required for correct behaviour so that a stray
edit doesn't silently revert a product decision.
"""
from __future__ import annotations

from app.ai.prompts import CLIENT_INSTRUCTIONS, CONTRACTOR_INSTRUCTIONS
from app.ai.tools import CONTRACTOR_TOOLS


def _register_client_description() -> str:
    tool = next(t for t in CONTRACTOR_TOOLS if t["name"] == "register_client")
    return tool["description"]


class TestContactAutosaveInstructions:
    def test_tool_description_allows_immediate_save_for_contact_share(self) -> None:
        desc = _register_client_description()
        assert "Contacto compartido" in desc
        assert "immediately" in desc or "no confirmation" in desc.lower()

    def test_tool_description_still_requires_confirmation_for_typed_input(self) -> None:
        desc = _register_client_description()
        assert "get confirmation" in desc

    def test_contractor_instructions_contain_contact_exception(self) -> None:
        assert "Contacto compartido" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_show_inline_confirmation_format(self) -> None:
        assert "Cliente guardado ✓" in CONTRACTOR_INSTRUCTIONS


class TestPostContactNextStepMenu:
    """After a contact-share save, Noa shows a 3-option next-step menu."""

    def test_contractor_instructions_show_next_step_question(self) -> None:
        assert "¿Qué quieres hacer con este contacto?" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_use_three_button_format(self) -> None:
        assert "(Agendar cita / Hacer presupuesto / Otro)" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_agendar_cita_asks_who_schedules(self) -> None:
        assert "Yo le escribo" in CONTRACTOR_INSTRUCTIONS
        assert "Pongo los detalles" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_bot_path_calls_initiate_appointment(self) -> None:
        assert "initiate_appointment" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_manual_path_calls_create_appointment(self) -> None:
        assert "create_appointment" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_presupuesto_path_calls_create_budget(self) -> None:
        assert "create_budget" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_otro_suggests_audio_or_text(self) -> None:
        # "Otro" path must not use buttons and must suggest a free-form voice/text message.
        instr = CONTRACTOR_INSTRUCTIONS.lower()
        assert "audio" in instr or "voz" in instr

    def test_register_client_tool_description_shows_next_step_menu(self) -> None:
        desc = _register_client_description()
        assert "Agendar cita" in desc
        assert "Hacer presupuesto" in desc
        assert "Otro" in desc

    def test_register_client_tool_description_skips_menu_for_typed_input(self) -> None:
        desc = _register_client_description()
        # Typed-input registration should not trigger the next-step menu.
        assert "do not offer the next-step menu" in desc.lower()


class TestTimeDisambiguation:
    def test_contractor_instructions_prompt_for_6_7_8(self) -> None:
        assert "6, 7, or 8" in CONTRACTOR_INSTRUCTIONS or "6, 7, 8" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_use_button_format(self) -> None:
        assert "Mañana / Tarde" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_no_prompt_for_9_to_12(self) -> None:
        assert "9–12" in CONTRACTOR_INSTRUCTIONS or "9-12" in CONTRACTOR_INSTRUCTIONS

    def test_contractor_instructions_no_prompt_for_1_to_5(self) -> None:
        assert "1–5" in CONTRACTOR_INSTRUCTIONS or "1-5" in CONTRACTOR_INSTRUCTIONS

    def test_client_instructions_prompt_for_6_7_8(self) -> None:
        assert "6, 7, or 8" in CLIENT_INSTRUCTIONS or "6, 7, 8" in CLIENT_INSTRUCTIONS

    def test_client_instructions_use_button_format(self) -> None:
        assert "Mañana / Tarde" in CLIENT_INSTRUCTIONS
