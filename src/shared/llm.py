import os
from typing import Optional, List, Any

from langchain_core.messages import SystemMessage
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI

deepseek = ChatDeepSeek(
    api_key=os.environ.get('DEEPSEEK_API_KEY') or 'dummy-key',
    model=os.environ.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash',
    reasoning_effort='low',
    temperature=0.0,#1.0,
    max_tokens=100000,
    timeout=None,
    max_retries=2,
    extra_body={
        'thinking': {
            'type': 'disabled'
        }
    },
)

gemini = ChatGoogleGenerativeAI(
    api_key=os.environ.get('GEMINI_API_KEY') or 'dummy-key',
    model=os.environ.get('GEMINI_MODEL') or 'gemini-flash-lite-latest',
    thinking_level='low',
    temperature=1.0,
    max_retries=2,
)

def get_llm(
    tools: Optional[List[Any]] = None,
    structured_output: Optional[Any] = None,
):
    """
    Returns a resilient LLM runnable with transparent fallback handling.
    Uses DeepSeek as the primary LLM and Gemini as the fallback LLM.
    If tools or structured_output are provided, they are bound to both primary and fallback models FIRST,
    and then with_fallbacks is applied AFTER.
    """
    primary = deepseek
    fallback = gemini

    if tools:
        primary = primary.bind_tools(tools)
        fallback = fallback.bind_tools(tools)

    if structured_output:
        primary = primary.with_structured_output(structured_output, strict=True)
        fallback = fallback.with_structured_output(structured_output)

    return primary.with_fallbacks([fallback])

