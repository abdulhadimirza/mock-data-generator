from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from shared.llm import (
    get_llm,
    deepseek_planner, gemini_planner,
    deepseek_code_gen, gemini_code_gen,
)
from ..common.utils import emit_progress
from ..state import GeneratorState
from .state import CodeGeneratorResponse
from .prompts import (
    stress_planner_system_prompt,
    code_generator_system_prompt,
)

# 0. Stress Planner Node
planner_llm = get_llm(primary=deepseek_planner, fallbacks=[gemini_planner])

def stress_planner_node(state: GeneratorState, config: RunnableConfig = None):
    emit_progress("Planning stress testing mock data strategy...")
    state_messages = state.get('messages', [])
    relevant_tables = state.get('relevant_tables', [])
    schema_map = state.get('schema_map', '')
    
    system_prompt = stress_planner_system_prompt
    if relevant_tables:
        system_prompt += f"\n\nRelevant tables identified for this request:\n<relevant_tables>\n{', '.join(relevant_tables)}\n</relevant_tables>"
    if schema_map:
        system_prompt += f"\n\nSchema map of relevant tables:\n<schema_map>\n{schema_map}\n</schema_map>"
        
    messages = [SystemMessage(content=system_prompt)] + list(state_messages)
    response = planner_llm.invoke(messages, config=config)
    return {'generated_plan': response.content}


# 1. Stress Code Generator Node
code_gen_llm = get_llm(primary=deepseek_code_gen, fallbacks=[gemini_code_gen], structured_output=CodeGeneratorResponse)

def code_generator_node(state: GeneratorState, config: RunnableConfig = None):
    current_retries = state.get('retry_count', 0)
    emit_progress(f"Generating Python data insertion script (Attempt {current_retries + 1})...")
    state_messages = state.get('messages', [])
    schema_map = state.get('schema_map', '')
    generated_plan = state.get('generated_plan', '')
    insertion_order = state.get('insertion_order', [])
    
    system_prompt = code_generator_system_prompt
    if insertion_order:
        system_prompt += f"\n\nStrict Table Insertion Order (Parent -> Child):\n<strict_insertion_order>\n{' -> '.join(insertion_order)}\n</strict_insertion_order>"
    if schema_map:
        system_prompt += f"\n\nTarget Database Schema:\n<target_database_schema>\n{schema_map}\n</target_database_schema>"
    if generated_plan:
        system_prompt += f"\n\nExecution Plan:\n<execution_plan>\n{generated_plan}\n</execution_plan>"
        
    prompt_messages = [SystemMessage(content=system_prompt)] + list(state_messages)
        
    response = code_gen_llm.invoke(prompt_messages, config=config)
    python_code = response.python_code
        
    return {
        'generated_code': python_code,
        'retry_count': current_retries + 1,
        'messages': [AIMessage(content=f"Generated Data Insertion Script:\n```python\n{python_code}\n```")]
    }
