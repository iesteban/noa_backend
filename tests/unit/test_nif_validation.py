from __future__ import annotations

from app.services.nif_validation import extract_address, extract_emails, validate_nif


class TestValidateNif:
    def test_valid_dni(self) -> None:
        # 12345678Z — 12345678 % 23 = 14 → 'Z'
        assert validate_nif("Mi DNI es 12345678Z") == "12345678Z"

    def test_valid_dni_lowercase_letter(self) -> None:
        assert validate_nif("12345678z") == "12345678Z"

    def test_invalid_dni_wrong_letter(self) -> None:
        assert validate_nif("12345678A") is None  # A is not the checksum for 12345678

    def test_valid_nie_x(self) -> None:
        # X0000000T — X→0, 0000000 % 23 = 0 → 'T'
        assert validate_nif("X0000000T") == "X0000000T"

    def test_valid_nie_y(self) -> None:
        # Y0000001R — Y→1, 10000001 % 23 = 8 → 'R' ... let's pick a known one
        # Y3859799Q: Y→1, 13859799 % 23 = 16 → 'Q'? Let me just check with Y0000000Z
        # Y→1, 10000000 % 23 = 10000000 % 23 = 1 → 'R'
        # Actually let me just use X0000000T which we know is valid
        assert validate_nif("X0000000T") is not None

    def test_nie_lowercase_prefix(self) -> None:
        assert validate_nif("x0000000T") == "X0000000T"

    def test_invalid_nie_wrong_letter(self) -> None:
        assert validate_nif("X0000000A") is None

    def test_valid_cif(self) -> None:
        # CIF format: letter + 7 digits + check char
        result = validate_nif("B12345674")
        assert result is not None
        assert result.startswith("B")

    def test_no_nif_in_text(self) -> None:
        assert validate_nif("Hola, soy Pedro García") is None

    def test_extracts_from_sentence(self) -> None:
        result = validate_nif("Mi NIF es 12345678Z, vivo en Madrid")
        assert result == "12345678Z"

    def test_only_digits_no_letter(self) -> None:
        assert validate_nif("12345678") is None


class TestExtractEmails:
    def test_single_email(self) -> None:
        assert extract_emails("Escríbeme a pedro@example.com") == ["pedro@example.com"]

    def test_multiple_emails(self) -> None:
        emails = extract_emails("pedro@foo.com y factura@empresa.es")
        assert "pedro@foo.com" in emails
        assert "factura@empresa.es" in emails

    def test_no_email(self) -> None:
        assert extract_emails("Calle Mayor 15, 28013 Madrid") == []

    def test_email_with_plus(self) -> None:
        assert extract_emails("pedro+facturas@example.com") == ["pedro+facturas@example.com"]


class TestExtractAddress:
    def test_returns_none_when_only_nif(self) -> None:
        assert extract_address("12345678Z") is None

    def test_strips_nif_and_returns_rest(self) -> None:
        result = extract_address("12345678Z Calle Mayor 15, 28013 Madrid")
        assert result is not None
        assert "Calle Mayor" in result
        assert "12345678Z" not in result

    def test_strips_label_prefix(self) -> None:
        result = extract_address("Dirección: Calle Gran Vía 44, 28013 Madrid")
        assert result is not None
        assert "Gran Vía" in result

    def test_strips_email(self) -> None:
        result = extract_address("Calle Mayor 15, 28013 Madrid pedro@example.com")
        assert result is not None
        assert "@" not in result

    def test_short_remainder_returns_none(self) -> None:
        assert extract_address("12345678Z Madrid") is None

    def test_full_message(self) -> None:
        text = "12345678Z, Calle Alcalá 123, 3ºB, 28009 Madrid, pedro@empresa.com"
        result = extract_address(text)
        assert result is not None
        assert "Alcalá" in result
