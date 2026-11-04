from app.domain.outlet import validate_radio_script, validate_sms, word_count
from app.domain.sms import is_gsm7, sms_segments


def test_gsm7_single_segment():
    assert sms_segments("x" * 160) == 1


def test_gsm7_two_segments():
    assert sms_segments("x" * 161) == 2
    assert sms_segments("x" * 306) == 2
    assert sms_segments("x" * 307) == 3


def test_gsm7_extended_chars_cost_two():
    assert sms_segments("{" * 80) == 1
    assert sms_segments("{" * 81) == 2


def test_unicode_single_segment():
    assert sms_segments("x" * 70) == 1  # ascii still GSM-7; boundary differs below
    assert sms_segments("ẹ" * 70) == 1


def test_unicode_two_segments():
    assert sms_segments("ẹ" * 71) == 2
    assert sms_segments("ẹ" * 134) == 2
    assert sms_segments("ẹ" * 135) == 3


def test_hausa_hooked_letters_are_unicode():
    assert is_gsm7("ɓ ɗ ƙ") is False
    assert sms_segments("Shiga ciki " + "ɓ" * 60) == 2


def test_yoruba_marks_are_unicode():
    assert is_gsm7("ẹ ọ ṣ") is False


def test_emoji_counts_surrogate_pair():
    assert sms_segments("🔥" * 35) == 1
    assert sms_segments("🔥" * 36) == 2


def test_is_gsm7_plain():
    assert is_gsm7("Hello 123!") is True


def test_word_count():
    assert word_count("  stay   indoors today ") == 3


def test_radio_valid():
    script = " ".join(["rest"] * 70)
    assert validate_radio_script(script) == []


def test_radio_boundaries():
    assert validate_radio_script(" ".join(["rest"] * 65)) == []
    assert validate_radio_script(" ".join(["rest"] * 75)) == []
    assert len(validate_radio_script(" ".join(["rest"] * 64))) == 1
    assert len(validate_radio_script(" ".join(["rest"] * 76))) == 1


def test_radio_rejects_abbreviations():
    script = " ".join(["rest"] * 69 + ["WHO"])
    errors = validate_radio_script(script)
    assert any("WHO" in e for e in errors)


def test_radio_rejects_digits():
    script = " ".join(["rest"] * 69 + ["11am"])
    errors = validate_radio_script(script)
    assert any("digits" in e for e in errors)


def test_sms_valid_and_empty():
    assert validate_sms("Drink water and rest in shade.") == []
    assert validate_sms("   ") != []


def test_sms_rejects_three_segments():
    assert validate_sms("x" * 400) != []
    assert validate_sms("x" * 300) == []
