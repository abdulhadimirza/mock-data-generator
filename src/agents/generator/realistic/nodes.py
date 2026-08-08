import ast
import traceback
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from shared.llm import (
    get_llm,
    deepseek_planner, gemini_planner,
    deepseek_utility_synthesizer, gemini_utility_synthesizer,
    deepseek_code_gen, gemini_code_gen,
    deepseek_ast_fixer, gemini_ast_fixer,
)
from ..common.utils import emit_progress
from ..state import GeneratorState
from .state import UtilityCodeResponse, CodeGeneratorResponse, SyntaxFixResponse
from .prompts import (
    realistic_planner_system_prompt,
    utility_synthesizer_system_prompt,
    realistic_code_generator_system_prompt,
    syntax_fixer_system_prompt,
)

# 0. Planner Node
planner_llm = get_llm(primary=deepseek_planner, fallbacks=[gemini_planner])

def realistic_planner_node(state: GeneratorState, config: RunnableConfig = None):
    emit_progress("Planning realistic analytics mock data strategy...")
    state_messages = state.get('messages', [])
    #relevant_tables = state.get('relevant_tables', [])
    schema_map = state.get('schema_map', '')
    
    system_prompt = realistic_planner_system_prompt
    #if relevant_tables:
    #    system_prompt += f"\n<relevant_tables>\n{', '.join(relevant_tables)}\n</relevant_tables>"
    if schema_map:
        system_prompt += f"\n\n<relevant_schema>\n{schema_map}\n</relevant_schema>"
        
    messages = [SystemMessage(content=system_prompt)] + list(state_messages)
    response = planner_llm.invoke(messages, config=config)
    return {'generated_plan': response.content}


# 1. Utility Helper Synthesizer Node
utility_llm = get_llm(
    primary=deepseek_utility_synthesizer,
    fallbacks=[gemini_utility_synthesizer],
    structured_output=UtilityCodeResponse,
    format='json',
)

def utility_synthesizer_node(state: GeneratorState, config: RunnableConfig = None):
    emit_progress("Synthesizing realistic data generator helper functions...")
    schema_map = state.get("schema_map", "")
    generated_plan = state.get("generated_plan", "")
    
    system_prompt = utility_synthesizer_system_prompt
    if schema_map:
        system_prompt += f"\n\n<relevant_schema>\n{schema_map}\n</relevant_schema>"
    if generated_plan:
        system_prompt += f"\n\n<execution_plan>\n{generated_plan}\n</execution_plan>"
        
    messages = [SystemMessage(content=system_prompt)]
    response = utility_llm.invoke(messages, config=config)
    
    utility_python_code = response.utility_python_code
    utility_stubs_code = response.utility_stubs_code

    return {"utility_code": utility_python_code, "utility_stubs_code": utility_stubs_code}


# 2. Realistic Code Generator Node
realistic_code_llm = get_llm(
    primary=deepseek_code_gen,
    fallbacks=[gemini_code_gen],
    structured_output=CodeGeneratorResponse,
    format='json',
)

def realistic_code_generator_node(state: GeneratorState, config: RunnableConfig = None):
    current_retries = state.get("retry_count", 0)
    emit_progress(f"Generating realistic database insertion script (Attempt {current_retries + 1})...")
    state_messages = state.get("messages", [])
    schema_map = state.get("schema_map", "")
    generated_plan = state.get("generated_plan", "")
    insertion_order = state.get("insertion_order", [])
    utility_code = state.get("utility_code", "")
    utility_stubs_code = state.get("utility_stubs_code", "")
    
    system_prompt = realistic_code_generator_system_prompt
    if utility_stubs_code:
        system_prompt += f"\n\n<utility_stubs_code>\n{utility_stubs_code}\n</utility_stubs_code>"
    if insertion_order:
        system_prompt += f"\n\n<strict_insertion_order>\n{' -> '.join(insertion_order)}\n</strict_insertion_order>"
    if schema_map:
        system_prompt += f"\n\n<relevant_schema>\n{schema_map}\n</relevant_schema>"
    if generated_plan:
        system_prompt += f"\n\n<execution_plan>\n{generated_plan}\n</execution_plan>"
        
    messages = [SystemMessage(content=system_prompt)]
    response = realistic_code_llm.invoke(messages, config=config)
    
    raw_loop_code = response.execution_python_code
    
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


# 3. AST Checker & Syntax Fixer Node Factories
def create_ast_checker_node(code_key: str):
    def ast_checker_node(state: GeneratorState):
        code = state.get(code_key, "")
        try:
            ast.parse(code)
            return {"ast_error": None, "ast_retry_count": 0}
        except SyntaxError as e:
            error_msg = f"SyntaxError in {code_key} at line {e.lineno}:\n{e.msg}\nContext:\n{e.text}"
            return {"ast_error": error_msg}
    return ast_checker_node


ast_fixer_llm = get_llm(
    primary=deepseek_ast_fixer,
    fallbacks=[gemini_ast_fixer],
    structured_output=SyntaxFixResponse,
    format="json",
)


def create_syntax_fixer_node(code_key: str):
    def syntax_fixer_node(state: GeneratorState, config: RunnableConfig = None):
        code = state.get(code_key, "")
        ast_error = state.get("ast_error", "")
        current_retries = state.get("ast_retry_count", 0)

        emit_progress(f"Attempting search & replace syntax repair for {code_key} (Attempt {current_retries + 1})...")

        numbered_lines = [
            f"{i + 1} | {line}" for i, line in enumerate(code.splitlines())
        ]
        numbered_code = "\n".join(numbered_lines)

        prompt = f"<code_with_line_numbers>\n{numbered_code}\n</code_with_line_numbers>\n\n<syntax_error>\n{ast_error}\n</syntax_error>"
        messages = [
            SystemMessage(content=syntax_fixer_system_prompt),
            HumanMessage(content=prompt)
        ]

        response = ast_fixer_llm.invoke(messages, config=config)

        fixed_code = code
        for patch in response.patches:
            if patch.search in fixed_code:
                fixed_code = fixed_code.replace(patch.search, patch.replace)

        return {
            code_key: fixed_code,
            "ast_retry_count": current_retries + 1
        }
    return syntax_fixer_node
