from unittest.mock import MagicMock
from pydantic import BaseModel
from shared.llm import (
    _resolve_structured_output_method,
    _build_structured_output_kwargs,
    get_llm,
    ChatDeepSeek,
    ChatGoogleGenerativeAI,
)


class SampleResponse(BaseModel):
    summary: str


def test_resolve_structured_output_method_deepseek():
    mock_deepseek = MagicMock(spec=ChatDeepSeek)
    assert _resolve_structured_output_method(mock_deepseek, "json") == "json_mode"
    assert _resolve_structured_output_method(mock_deepseek, "strict") == "function_calling"
    assert _resolve_structured_output_method(mock_deepseek, "schema") == "function_calling"
    assert _resolve_structured_output_method(mock_deepseek, None) is None


def test_resolve_structured_output_method_gemini():
    mock_gemini = MagicMock(spec=ChatGoogleGenerativeAI)
    assert _resolve_structured_output_method(mock_gemini, "json") == "json_schema"
    assert _resolve_structured_output_method(mock_gemini, "strict") == "json_schema"
    assert _resolve_structured_output_method(mock_gemini, "schema") == "json_schema"
    assert _resolve_structured_output_method(mock_gemini, None) is None


def test_build_structured_output_kwargs():
    mock_deepseek = MagicMock(spec=ChatDeepSeek)
    mock_gemini = MagicMock(spec=ChatGoogleGenerativeAI)

    assert _build_structured_output_kwargs(mock_deepseek, "json") == {"method": "json_mode"}
    assert _build_structured_output_kwargs(mock_deepseek, "strict") == {"method": "function_calling", "strict": True}
    assert _build_structured_output_kwargs(mock_gemini, "json") == {"method": "json_schema", "strict": True}


def test_get_llm_with_format_json():
    mock_primary = MagicMock(spec=ChatDeepSeek)
    mock_fallback = MagicMock(spec=ChatGoogleGenerativeAI)

    get_llm(
        primary=mock_primary,
        fallbacks=[mock_fallback],
        structured_output=SampleResponse,
        format="json",
    )

    mock_primary.with_structured_output.assert_called_once_with(
        SampleResponse, method="json_mode"
    )
    mock_fallback.with_structured_output.assert_called_once_with(
        SampleResponse, strict=True, method="json_schema"
    )


def test_get_llm_with_format_strict():
    mock_primary = MagicMock(spec=ChatDeepSeek)
    mock_fallback = MagicMock(spec=ChatGoogleGenerativeAI)

    get_llm(
        primary=mock_primary,
        fallbacks=[mock_fallback],
        structured_output=SampleResponse,
        format="strict",
    )

    mock_primary.with_structured_output.assert_called_once_with(
        SampleResponse, strict=True, method="function_calling"
    )
    mock_fallback.with_structured_output.assert_called_once_with(
        SampleResponse, strict=True, method="json_schema"
    )
