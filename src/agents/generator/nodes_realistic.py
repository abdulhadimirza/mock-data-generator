from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from shared.llm import (
    get_llm,
    deepseek_utility_synthesizer, gemini_utility_synthesizer,
    deepseek_code_gen, gemini_code_gen,
)
from .prompts import (
    utility_synthesizer_system_prompt,
    realistic_code_generator_system_prompt,
)
from .state import (
    GeneratorState,
    UtilityCodeResponse,
    CodeGeneratorResponse,
)
from .nodes import emit_progress


# 1. Utility Helper Synthesizer Node
utility_llm = get_llm(
    primary=deepseek_utility_synthesizer,
    fallbacks=[gemini_utility_synthesizer],
    structured_output=UtilityCodeResponse,
    format="json",
)


def utility_synthesizer_node(state: GeneratorState, config: RunnableConfig = None):
    emit_progress("Synthesizing realistic data generator helper functions...")
    schema_map = state.get("schema_map", "")
    generated_plan = state.get("generated_plan", "")
    
    prompt = utility_synthesizer_system_prompt
    if schema_map:
        prompt += f"\n\nTarget Database Schema:\n<target_database_schema>\n{schema_map}\n</target_database_schema>"
    if generated_plan:
        prompt += f"\n\nExecution Plan:\n<execution_plan>\n{generated_plan}\n</execution_plan>"
        
    messages = [SystemMessage(content=prompt)]
    response = utility_llm.invoke(messages, config=config)
    
    utility_python_code = response.utility_python_code
    return {"utility_code": utility_python_code}


# 2. Realistic Code Generator Node
realistic_code_llm = get_llm(
    primary=deepseek_code_gen,
    fallbacks=[gemini_code_gen],
    structured_output=CodeGeneratorResponse,
    format="json",
)

def realistic_code_generator_node(state: GeneratorState, config: RunnableConfig = None):
    current_retries = state.get("retry_count", 0)
    emit_progress(f"Generating realistic database insertion script (Attempt {current_retries + 1})...")
    state_messages = state.get("messages", [])
    schema_map = state.get("schema_map", "")
    generated_plan = state.get("generated_plan", "")
    insertion_order = state.get("insertion_order", [])
    utility_code = state.get("utility_code", "")
    
    system_prompt = realistic_code_generator_system_prompt
    if utility_code:
        system_prompt += f"\n\nAvailable Utility Functions:\n<utility_code>\n{utility_code}\n</utility_code>"
    if insertion_order:
        system_prompt += f"\n\nStrict Table Insertion Order (Parent -> Child):\n<strict_insertion_order>\n{' -> '.join(insertion_order)}\n</strict_insertion_order>"
    if schema_map:
        system_prompt += f"\n\nTarget Database Schema:\n<target_database_schema>\n{schema_map}\n</target_database_schema>"
    if generated_plan:
        system_prompt += f"\n\nExecution Plan:\n<execution_plan>\n{generated_plan}\n</execution_plan>"
        
    prompt_messages = [SystemMessage(content=system_prompt)] + list(state_messages)
    response = realistic_code_llm.invoke(prompt_messages, config=config)
    
    raw_loop_code = response.python_code
    
    # Prepend utility functions to build the final executable script
    code_blocks = []
    if utility_code and utility_code.strip():
        code_blocks.append(utility_code.strip())
    if raw_loop_code and raw_loop_code.strip():
        code_blocks.append(raw_loop_code.strip())
        
    final_python_code = "\n\n".join(code_blocks)
    
    return {
        "generated_code": final_python_code,
        "retry_count": current_retries + 1,
        "messages": [AIMessage(content=f"Generated Data Insertion Script:\n```python\n{final_python_code}\n```")]
    }
