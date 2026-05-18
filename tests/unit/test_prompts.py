"""Regression guards for prompt and tool-description content.

These tests don't call Claude — they verify that the strings Claude sees
contain the instructions required for correct behaviour so that a stray
edit doesn't silently revert a product decision.
"""
from __future__ import annotations

from app.ai.prompts import CONTRACTOR_INSTRUCTIONS
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
