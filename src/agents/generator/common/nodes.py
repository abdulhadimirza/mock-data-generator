from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END

from shared.tools import list_tables, get_table_metadata_with_deps, format_metadata_to_sql_json, get_topological_table_order
from shared.llm import (
    get_llm,
    deepseek_infer, gemini_infer,
    deepseek_filter, gemini_filter,
    deepseek_summary, gemini_summary,
)
from ..state import GeneratorState, CodeGeneratorIntentResponse, TableSelectionResponse
from ..sandbox import run_in_isolated_sandbox
from .utils import emit_progress, _extract_initial_user_request
from .prompts import (
    generator_infer_system_prompt,
    generator_filter_system_prompt,
    generator_summary_system_prompt,
)


# 0. Intent Inference Node
infer_llm = get_llm(primary=deepseek_infer, fallbacks=[gemini_infer], structured_output=CodeGeneratorIntentResponse)
def infer_intent_node(state: GeneratorState, config: RunnableConfig = None):
    emit_progress("Inferring generation mode intent...")
    state_messages = state.get('messages', [])
    messages = [SystemMessage(content=generator_infer_system_prompt)] + list(state_messages)
    
    result = infer_llm.invoke(messages, config=config)
    generation_mode = result.generation_mode
    
    emit_progress(f"Inferred generation mode: {generation_mode}")
    return {'generation_mode': generation_mode}


# 1. Stateless Filter Node
filter_llm = get_llm(primary=deepseek_filter, fallbacks=[gemini_filter], structured_output=TableSelectionResponse)
def filter_tables_node(state: GeneratorState, config: RunnableConfig = None):
    emit_progress("Filtering relevant database tables...")
    tables = list_tables.invoke({})
    filter_prompt = generator_filter_system_prompt.format(tables=tables)
    state_messages = state.get('messages', [])
    messages = [SystemMessage(content=filter_prompt)] + list(state_messages)
    
    result = filter_llm.invoke(messages, config=config)

    relevant_tables = result.relevant_tables
    
    return {'relevant_tables': relevant_tables}


# 2. Fetch Schema Node
def fetch_schema_node(state: GeneratorState):
    relevant_tables = state.get('relevant_tables', [])
    if not relevant_tables:
        return {'schema_map': '', 'insertion_order': []}
    
    emit_progress(f"Fetching schema for target tables: {', '.join(relevant_tables)}...")
    schema_metadata = get_table_metadata_with_deps(relevant_tables)
    
    try:
        insertion_order = get_topological_table_order(schema_metadata)
        if insertion_order:
            emit_progress(f"Calculated FK topological insertion order: {' -> '.join(insertion_order)}")
    except Exception:
        insertion_order = []

    schema_map_str = format_metadata_to_sql_json(schema_metadata)

    return {
        'schema_map': schema_map_str,
        'insertion_order': insertion_order
    }


# 5. Sandbox Execution Node (Shared across subgraphs)
def sandbox_execution_node(state: GeneratorState):
    emit_progress("Executing generated script in sandbox environment...")
    code = state.get('generated_code', '')
    if not code:
        emit_progress("Sandbox Execution Error: No code provided.")
        return {
            'execution_result': "No code provided to execute.",
            'execution_error': "Empty generated code."
        }

    success, message = run_in_isolated_sandbox(code, timeout_seconds=15)

    if success:
        emit_progress("Sandbox script execution succeeded!")
        return {
            'execution_result': message,
            'execution_error': None
        }
    else:
        if "TimeoutError" in message:
            emit_progress("Sandbox execution timed out.")
        else:
            emit_progress(f"Sandbox execution error: {message[:60]}...")
            
        error_feedback = f"[Sandbox Execution Feedback]\nThe previous script execution failed with error:\n<execution_error>\n{message}\n</execution_error>\nPlease analyze the error and the failed script, fix the bug, and return updated executable Python code."
        return {
            'execution_result': f"Execution failed: {message}",
            'execution_error': message,
            'messages': [HumanMessage(content=error_feedback)]
        }


# 6. Summary Node
summary_llm = get_llm(primary=deepseek_summary, fallbacks=[gemini_summary])
def summary_node(state: GeneratorState, config: RunnableConfig = None):
    emit_progress("Generating final summary...")
    state_messages = state.get('messages', [])
    relevant_tables = state.get('relevant_tables', [])
    execution_result = state.get('execution_result', '')
    execution_error = state.get('execution_error', None)
    generated_plan = state.get('generated_plan', '')
    
    if execution_error:
        execution_status = f"<status>FAILED</status>\n<error_details>\n{execution_error}\n</error_details>"
    else:
        execution_status = f"<status>SUCCESS</status>\n<execution_output>\n{execution_result}\n</execution_output>"
        
    user_req = _extract_initial_user_request(state_messages)
    user_req_text = user_req.content if (user_req and hasattr(user_req, 'content')) else "Generate mock data"

    summary_prompt = generator_summary_system_prompt.format(
        user_request=user_req_text,
        relevant_tables=", ".join(relevant_tables) if relevant_tables else "None specified",
        executed_plan=generated_plan if generated_plan else "No plan provided.",
        execution_status=execution_status,
    )
    messages = [SystemMessage(content=summary_prompt)]

    response = summary_llm.invoke(messages, config=config)
    return {'messages': [response]}


# 7. Subgraph Retry Router
def subgraph_route_execution(state: GeneratorState):
    execution_error = state.get('execution_error', None)
    retry_count = state.get('retry_count', 0)
    
    if execution_error and retry_count < 3:
        emit_progress(f"Execution error detected. Routing back to code generation ({retry_count}/3)...")
        return 'code_generator'
    return END
