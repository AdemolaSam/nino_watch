from app.llm.schemas import AdvisoryContent
from app.services.advisory import build_translation_user, content_hash_for, is_tested


def test_is_tested_english_always():
    assert is_tested("en") is True


def test_is_tested_unreviewed_candidate():
    assert is_tested("ha") is False


def test_is_tested_unknown():
    assert is_tested("xx") is False


def test_content_hash_stable():
    content = AdvisoryContent(happening="H", atRisk="R", actions="A")
    assert content_hash_for(content) == content_hash_for(content)
    other = AdvisoryContent(happening="H2", atRisk="R", actions="A")
    assert content_hash_for(content) != content_hash_for(other)


def test_translation_user_names_language():
    content = AdvisoryContent(happening="H", atRisk="R", actions="A")
    user = build_translation_user(content, "ha")
    assert "Hausa (ha)" in user
    assert '"happening": "H"' in user
