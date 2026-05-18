"""Unit tests for error-report intent detection and language helpers."""
from __future__ import annotations

from app.services.error_report import detect_error_intent, detect_language


class TestDetectErrorIntent:
    # --- Commands ---
    def test_slash_error_no_description(self) -> None:
        assert detect_error_intent("/error") == (True, None)

    def test_slash_reporte_no_description(self) -> None:
        assert detect_error_intent("/reporte") == (True, None)

    def test_slash_error_uppercase_no_description(self) -> None:
        assert detect_error_intent("/ERROR") == (True, None)

    def test_slash_error_with_inline_description(self) -> None:
        is_error, desc = detect_error_intent("/error la factura está mal")
        assert is_error is True
        assert desc == "la factura está mal"

    def test_slash_reporte_with_inline_description(self) -> None:
        is_error, desc = detect_error_intent("/reporte la fecha es incorrecta")
        assert is_error is True
        assert desc == "la fecha es incorrecta"

    # --- Keywords ---
    def test_keyword_error_exact(self) -> None:
        assert detect_error_intent("error") == (True, None)

    def test_keyword_esta_mal_exact(self) -> None:
        assert detect_error_intent("está mal") == (True, None)

    def test_keyword_esta_mal_no_accent(self) -> None:
        is_error, _ = detect_error_intent("esta mal")
        assert is_error is True

    def test_keyword_esta_mal_uppercase(self) -> None:
        is_error, _ = detect_error_intent("ESTÁ MAL")
        assert is_error is True

    def test_keyword_incorrecto_exact(self) -> None:
        assert detect_error_intent("incorrecto") == (True, None)

    def test_keyword_falla_exact(self) -> None:
        assert detect_error_intent("falla") == (True, None)

    def test_keyword_no_funciona_exact(self) -> None:
        assert detect_error_intent("no funciona") == (True, None)

    def test_keyword_eso_no_es_asi(self) -> None:
        is_error, _ = detect_error_intent("eso no es así")
        assert is_error is True

    def test_keyword_te_has_equivocado(self) -> None:
        is_error, _ = detect_error_intent("te has equivocado")
        assert is_error is True

    def test_keyword_esta_equivocado(self) -> None:
        is_error, _ = detect_error_intent("está equivocado")
        assert is_error is True

    def test_keyword_with_context_returns_full_message(self) -> None:
        is_error, desc = detect_error_intent("está mal la cantidad cobrada")
        assert is_error is True
        assert desc == "está mal la cantidad cobrada"

    def test_error_keyword_with_context_returns_full_message(self) -> None:
        is_error, desc = detect_error_intent("error, la fecha es del año pasado")
        assert is_error is True
        assert desc == "error, la fecha es del año pasado"

    def test_falla_with_context(self) -> None:
        is_error, desc = detect_error_intent("falla el cálculo del IVA")
        assert is_error is True
        assert desc == "falla el cálculo del IVA"

    # --- Post-document "no" ---
    def test_no_after_invoice_generation(self) -> None:
        last = "Factura generada. ¿Se la envío a Pedro ahora?"
        assert detect_error_intent("no", last) == (True, None)

    def test_no_after_budget_generation(self) -> None:
        last = "Presupuesto generado. ¿Lo envío a Ana?"
        assert detect_error_intent("no", last) == (True, None)

    def test_no_without_last_message(self) -> None:
        assert detect_error_intent("no") == (False, None)

    def test_no_after_non_document_message(self) -> None:
        last = "¿Qué más necesitas?"
        assert detect_error_intent("no", last) == (False, None)

    def test_incorrecto_after_document(self) -> None:
        last = "Factura generada. ¿Se la envío?"
        is_error, _ = detect_error_intent("incorrecto", last)
        assert is_error is True

    # --- No false positives ---
    def test_normal_greeting_not_detected(self) -> None:
        assert detect_error_intent("Hola, ¿cómo estás?") == (False, None)

    def test_work_log_not_detected(self) -> None:
        assert detect_error_intent("Estuve 2 horas con Pedro cambiando un grifo") == (False, None)

    def test_no_in_sentence_not_detected(self) -> None:
        assert detect_error_intent("no tengo clientes nuevos") == (False, None)

    def test_no_in_sentence_without_document_context(self) -> None:
        last = "Listando facturas pendientes..."
        assert detect_error_intent("no hay facturas", last) == (False, None)


class TestDetectLanguage:
    def test_spanish_with_accented_vowel(self) -> None:
        assert detect_language("está mal") == "es"

    def test_spanish_with_ñ(self) -> None:
        assert detect_language("año") == "es"

    def test_spanish_keyword_no_accent(self) -> None:
        assert detect_language("error") == "es"

    def test_english_text(self) -> None:
        assert detect_language("this is wrong") == "en"

    def test_english_correction(self) -> None:
        assert detect_language("that date is wrong") == "en"
