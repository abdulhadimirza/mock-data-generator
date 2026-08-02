import os
from typing import Optional, List, Dict, Any, Literal, Union

from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_core.runnables import RunnableWithFallbacks
from langchain_core.language_models import BaseChatModel

DeepSeekReasoningEffort = Literal['disabled', 'low', 'high', 'xhigh', 'max']
GeminiThinkingLevel = Literal['minimal', 'low', 'medium', 'high']


def create_deepseek_llm(
    reasoning_effort: DeepSeekReasoningEffort = 'disabled',
    temperature: float = 1.0,
    model: str = 'deepseek-v4-flash',
) -> ChatDeepSeek:
    kwargs: Dict[str, Any] = {
        'api_key': os.environ.get('DEEPSEEK_API_KEY'),
        'model': model,
        'max_tokens': 100000,
        'timeout': None,
        'max_retries': 2,
        'temperature': temperature,
    }
    if reasoning_effort == 'disabled':
        kwargs['extra_body'] = {
            'thinking': {
                'type': 'disabled'
            }
        }
    else:
        kwargs['reasoning_effort'] = reasoning_effort
        kwargs['extra_body'] = {
            'thinking': {
                'type': 'enabled'
            }
        }
    return ChatDeepSeek(**kwargs)


def create_gemini_llm(
    thinking_level: GeminiThinkingLevel = 'low',
    model: str = 'gemini-flash-lite-latest',
) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        api_key=os.environ.get('GEMINI_API_KEY'),
        model=model,
        thinking_level=thinking_level,
        temperature=1.0,
        max_retries=2,
    )


# Base / Default Lowest Thinking Models
deepseek_lowest_thinking: ChatDeepSeek = create_deepseek_llm(reasoning_effort='disabled', temperature=1.0)
gemini_lowest_thinking: ChatGoogleGenerativeAI = create_gemini_llm(thinking_level='minimal')

# Generator Subagent Node Configs
deepseek_filter: ChatDeepSeek = create_deepseek_llm(reasoning_effort='disabled', temperature=1.0)
gemini_filter: ChatGoogleGenerativeAI = create_gemini_llm(thinking_level='minimal')

deepseek_planner: ChatDeepSeek = create_deepseek_llm(reasoning_effort='high', temperature=1.0)
gemini_planner: ChatGoogleGenerativeAI = create_gemini_llm(thinking_level='high')

deepseek_code_gen: ChatDeepSeek = create_deepseek_llm(reasoning_effort='high', temperature=0.0)
gemini_code_gen: ChatGoogleGenerativeAI = create_gemini_llm(thinking_level='minimal')

deepseek_summary: ChatDeepSeek = create_deepseek_llm(reasoning_effort='disabled', temperature=0.0)
gemini_summary: ChatGoogleGenerativeAI = create_gemini_llm(thinking_level='minimal')

# Other Subagents Node Configs
deepseek_editor: ChatDeepSeek = create_deepseek_llm(reasoning_effort='disabled', temperature=0.0) # Temporary
gemini_editor: ChatGoogleGenerativeAI = create_gemini_llm(thinking_level='minimal') # Temporary

deepseek_reader: ChatDeepSeek = create_deepseek_llm(reasoning_effort='disabled', temperature=0.0)
gemini_reader: ChatGoogleGenerativeAI = create_gemini_llm(thinking_level='minimal')

deepseek_supervisor: ChatDeepSeek = create_deepseek_llm(reasoning_effort='disabled', temperature=1.3)
gemini_supervisor: ChatGoogleGenerativeAI = create_gemini_llm(thinking_level='minimal')


# Model Fallback Configuration Flag
# Set to True to make Gemini primary and DeepSeek fallback across all agents.
USE_GEMINI_AS_PRIMARY: bool = os.environ.get("USE_GEMINI_AS_PRIMARY", "False").lower() in ("true", "1", "yes")


def get_llm(
    primary: BaseChatModel,
    fallbacks: Optional[List[BaseChatModel]] = None,
    tools: Optional[List[Any]] = None,
    structured_output: Optional[Any] = None,
) -> Union[BaseChatModel, RunnableWithFallbacks]:
    """
    Returns a resilient LLM runnable with transparent fallback handling.
    If USE_GEMINI_AS_PRIMARY is True, primary and fallback models are swapped.
    If tools or structured_output are provided, they are bound to primary and fallback models FIRST,
    and then with_fallbacks is applied AFTER.
    """
    if USE_GEMINI_AS_PRIMARY and fallbacks:
        primary, fallbacks = fallbacks[0], [primary] + fallbacks[1:]

    if tools:
        primary = primary.bind_tools(tools)
        if fallbacks:
            fallbacks = [f.bind_tools(tools) for f in fallbacks]

    if structured_output:
        primary = primary.with_structured_output(structured_output, strict=True)
        if fallbacks:
            fallbacks = [f.with_structured_output(structured_output, strict=True) for f in fallbacks]

    return primary.with_fallbacks(fallbacks) if fallbacks else primary


