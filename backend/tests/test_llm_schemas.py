import pytest

from app.llm.schemas import (
    ExtractionResult,
    LlmParseError,
    MatchSignal,
    TranslationResult,
    parse_json,
    strip_fences,
)


def test_strip_fences_plain():
    assert strip_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fences_markdown():
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_parse_extraction():
    result = parse_json(
        '{"is_relevant": true, "event_type": "flood", "evidence_quote": "river overflowed",'
        ' "language": "ha", "confidence": 0.8}',
        ExtractionResult,
    )
    assert isinstance(result, ExtractionResult)
    assert result.event_type == "flood"
    assert result.confidence == 0.8


def test_parse_extraction_irrelevant_minimal():
    result = parse_json('{"is_relevant": false}', ExtractionResult)
    assert isinstance(result, ExtractionResult)
    assert result.is_relevant is False
    assert result.event_type is None


def test_parse_invalid_json_raises():
    with pytest.raises(LlmParseError):
        parse_json("not json", ExtractionResult)


def test_parse_wrong_shape_raises():
    with pytest.raises(LlmParseError):
        parse_json('{"event_type": "flood"}', ExtractionResult)


def test_parse_match_signal():
    result = parse_json('{"match": true, "reason": "same place and date"}', MatchSignal)
    assert isinstance(result, MatchSignal)
    assert result.match is True


def test_parse_translation_camel_alias():
    result = parse_json(
        '{"happening": "Hot.", "atRisk": "Workers.", "actions": "Rest."}',
        TranslationResult,
    )
    assert isinstance(result, TranslationResult)
    assert result.at_risk == "Workers."
