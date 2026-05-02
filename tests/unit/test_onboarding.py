"""Unit tests for onboarding helpers — no DB required."""
from __future__ import annotations

from app.services.onboarding import validate_nif


class TestValidateNif:
    # Valid NIF (8 digits + letter)
    def test_valid_nif(self) -> None:
        assert validate_nif("12345678Z") is True

    def test_valid_nif_lowercase_normalized(self) -> None:
        assert validate_nif("12345678z") is True

    def test_valid_nif_with_spaces(self) -> None:
        assert validate_nif("1234 5678 Z") is True

    def test_valid_nif_with_dash(self) -> None:
        assert validate_nif("12345678-Z") is True

    # Valid NIE (X/Y/Z + 7 digits + letter)
    def test_valid_nie_x(self) -> None:
        assert validate_nif("X1234567L") is True

    def test_valid_nie_y(self) -> None:
        assert validate_nif("Y1234567L") is True

    def test_valid_nie_z(self) -> None:
        assert validate_nif("Z1234567L") is True

    def test_valid_nie_lowercase(self) -> None:
        assert validate_nif("x1234567l") is True

    # Valid CIF (letter + 7 digits + letter or digit)
    def test_valid_cif_ending_letter(self) -> None:
        assert validate_nif("B12345678") is True

    def test_valid_cif_ending_digit(self) -> None:
        assert validate_nif("A12345670") is True

    def test_valid_cif_various_prefixes(self) -> None:
        for letter in "ABCDEFGHJNPQRSUVW":
            assert validate_nif(f"{letter}1234567A") is True

    # Invalid formats
    def test_invalid_too_short(self) -> None:
        assert validate_nif("1234567Z") is False

    def test_invalid_too_long(self) -> None:
        assert validate_nif("123456789Z") is False

    def test_invalid_no_letter_suffix(self) -> None:
        assert validate_nif("123456789") is False

    def test_invalid_empty(self) -> None:
        assert validate_nif("") is False

    def test_invalid_all_letters(self) -> None:
        assert validate_nif("ABCDEFGHZ") is False

    def test_invalid_letter_not_in_any_set(self) -> None:
        # I is not a valid NIE prefix (X/Y/Z), not a CIF prefix (ABCDEFGHJNPQRSUVW),
        # and not a digit, so it matches no valid format
        assert validate_nif("I1234567L") is False

    def test_invalid_special_chars(self) -> None:
        assert validate_nif("1234#678Z") is False
