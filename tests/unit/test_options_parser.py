"""Unit tests for app.messaging.options.parse_options."""
from __future__ import annotations

from app.messaging.options import parse_options


class TestParenthesisedOptions:
    def test_two_options(self) -> None:
        text, opts = parse_options("¿Lo agendo? (Sí / No)")
        assert opts == ["Sí", "No"]
        assert text == "¿Lo agendo?"

    def test_three_options(self) -> None:
        text, opts = parse_options("Anotado ✓\n¿Lo guardo? (Sí / No / Editar)")
        assert opts == ["Sí", "No", "Editar"]
        assert "¿Lo guardo?" in text
        assert "(Sí / No / Editar)" not in text

    def test_options_stripped_from_display_text(self) -> None:
        text, opts = parse_options("Factura generada. ¿Se la envío a Pedro ahora? (Sí / No)")
        assert opts == ["Sí", "No"]
        assert text == "Factura generada. ¿Se la envío a Pedro ahora?"

    def test_extra_whitespace_around_slashes(self) -> None:
        _, opts = parse_options("¿Continuar? (Sí  /  No)")
        assert opts == ["Sí", "No"]

    def test_single_option_in_parens_ignored(self) -> None:
        text, opts = parse_options("Usa el formato (PDF)")
        assert opts is None
        assert text == "Usa el formato (PDF)"

    def test_options_mid_text_ignored(self) -> None:
        # Parens in the middle are not option lists.
        text, opts = parse_options("Elige (uno) o dos opciones y avísame")
        assert opts is None


class TestNumberedListOptions:
    def test_two_items(self) -> None:
        text, opts = parse_options("¿Cuál Pedro?\n1. Pedro Mejuto\n2. Pedro Sánchez")
        assert opts == ["Pedro Mejuto", "Pedro Sánchez"]
        assert text == "¿Cuál Pedro?"

    def test_three_items(self) -> None:
        raw = (
            "¿Con quién quieres contactar?\n"
            "1. Fontanería García\n"
            "2. Electricista Ruiz\n"
            "3. Carpintería Leal"
        )
        text, opts = parse_options(raw)
        assert opts == ["Fontanería García", "Electricista Ruiz", "Carpintería Leal"]
        assert text == "¿Con quién quieres contactar?"

    def test_prefix_lines_preserved(self) -> None:
        raw = "Tengo dos Pedros:\n1. Pedro Alonso\n2. Pedro Ruiz"
        text, opts = parse_options(raw)
        assert text == "Tengo dos Pedros:"
        assert opts == ["Pedro Alonso", "Pedro Ruiz"]

    def test_single_numbered_line_ignored(self) -> None:
        # A lone "1. Something" is not a list.
        text, opts = parse_options("Pista 1. Fíjate en el número de factura.")
        assert opts is None

    def test_non_consecutive_numbers_ignored(self) -> None:
        # Regex matches the last block of numbered lines; non-consecutive numbering
        # still matches as long as the lines end the text.
        text, opts = parse_options("Aviso:\n1. Primera cosa\n3. Tercera cosa")
        assert opts == ["Primera cosa", "Tercera cosa"]


class TestNoOptions:
    def test_plain_text_unchanged(self) -> None:
        msg = "Trabajo guardado. Importe: 80€."
        text, opts = parse_options(msg)
        assert text == msg
        assert opts is None

    def test_empty_string(self) -> None:
        text, opts = parse_options("")
        assert text == ""
        assert opts is None

    def test_question_without_explicit_options(self) -> None:
        text, opts = parse_options("¿Qué facturas están sin pagar?")
        assert opts is None

    def test_multiline_without_list(self) -> None:
        msg = "Anotado ✓\nCliente: Ana García\nImporte: 120€"
        text, opts = parse_options(msg)
        assert text == msg
        assert opts is None
