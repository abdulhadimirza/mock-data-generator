import os
from typing import Optional, List, Any

from langchain_core.messages import SystemMessage
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI

deepseek = ChatDeepSeek(
    api_key=os.environ.get('DEEPSEEK_API_KEY') or 'dummy-key',
    model=os.environ.get('DEEPSEEK_MODEL') or 'deepseek-v4-flash',
    reasoning_effort='low',
    temperature=1.0,
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

def get_llm(tools: Optional[List[Any]] = None):
    """
    Returns a resilient LLM runnable with transparent fallback handling.
    Uses Gemini as the primary LLM and DeepSeek as the fallback LLM.
    If tools are provided, tools are bound to both primary and fallback models.
    """
    if tools:
        primary = deepseek.bind_tools(tools)#gemini.bind_tools(tools)
        fallback = gemini.bind_tools(tools)#deepseek.bind_tools(tools)
        return primary.with_fallbacks([fallback])
    return deepseek.with_fallbacks([gemini])#gemini.with_fallbacks([deepseek])
