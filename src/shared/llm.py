import os
from typing import Optional, List, Any

from langchain_core.messages import SystemMessage
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI

def create_deepseek_llm(reasoning_effort: str = 'low', temperature: float = 1.0) -> ChatDeepSeek:
    kwargs = {
        'api_key': os.environ.get('DEEPSEEK_API_KEY') or 'dummy-key',
        'model': os.environ.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash',
        'max_tokens': 100000,
        'timeout': None,
        'max_retries': 2,
    }
    if reasoning_effort == 'low':
        kwargs['reasoning_effort'] = 'low'
        kwargs['temperature'] = temperature
        kwargs['extra_body'] = {
            'thinking': {
                'type': 'disabled'
            }
        }
    elif reasoning_effort == 'high':
        kwargs['reasoning_effort'] = 'high'
        kwargs['extra_body'] = {
            'thinking': {
                'type': 'enabled'
            }
        }
    return ChatDeepSeek(**kwargs)


def create_gemini_llm(thinking_level: str = 'low') -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        api_key=os.environ.get('GEMINI_API_KEY') or 'dummy-key',
        model=os.environ.get('GEMINI_MODEL') or 'gemini-flash-lite-latest',
        thinking_level=thinking_level,
        temperature=1.0,
        max_retries=2,
    )


# Base / Default Lowest Thinking Models
deepseek_lowest_thinking = create_deepseek_llm(reasoning_effort='low', temperature=1.0)
gemini_lowest_thinking = create_gemini_llm(thinking_level='low')

# Generator Subagent Node Configs
deepseek_filter = create_deepseek_llm(reasoning_effort='low', temperature=1.0)
gemini_filter = create_gemini_llm(thinking_level='low')

deepseek_planner = create_deepseek_llm(reasoning_effort='high', temperature=1.0)
gemini_planner = create_gemini_llm(thinking_level='high')

deepseek_code_gen = create_deepseek_llm(reasoning_effort='high', temperature=0.0)
gemini_code_gen = create_gemini_llm(thinking_level='high')

deepseek_summary = create_deepseek_llm(reasoning_effort='low', temperature=1.3)
gemini_summary = create_gemini_llm(thinking_level='low')

# Other Subagents Node Configs
deepseek_editor = create_deepseek_llm(reasoning_effort='low', temperature=0.0)
gemini_editor = create_gemini_llm(thinking_level='low')

deepseek_reader = create_deepseek_llm(reasoning_effort='low', temperature=0.0)
gemini_reader = create_gemini_llm(thinking_level='low')

deepseek_supervisor = create_deepseek_llm(reasoning_effort='low', temperature=1.3)
gemini_supervisor = create_gemini_llm(thinking_level='low')


def get_llm(
    primary: Any,
    fallbacks: Optional[List[Any]] = None,
    tools: Optional[List[Any]] = None,
    structured_output: Optional[Any] = None,
):
    """
    Returns a resilient LLM runnable with transparent fallback handling.
    If tools or structured_output are provided, they are bound to primary and fallback models FIRST,
    and then with_fallbacks is applied AFTER.
    """
    if tools:
        primary = primary.bind_tools(tools)
        if fallbacks:
            fallbacks = [f.bind_tools(tools) for f in fallbacks]

    if structured_output:
        primary = primary.with_structured_output(structured_output, strict=True)
        if fallbacks:
            fallbacks = [f.with_structured_output(structured_output, strict=True) for f in fallbacks]

    return primary.with_fallbacks(fallbacks) if fallbacks else primary

