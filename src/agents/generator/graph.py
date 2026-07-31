import sys
import io
import multiprocessing
import queue
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer

from shared.tools import list_tables, get_tables_schema_with_deps
from shared.llm import get_llm
from .prompts import (
    generator_planner_system_prompt,
    code_generator_system_prompt,
    generator_summary_system_prompt,
)
from .state import GeneratorState, TableSelectionResponse, CodeGeneratorResponse
from .sandbox import run_in_sandbox

# Top-level LLM Instantiation
filter_llm = get_llm().with_structured_output(TableSelectionResponse)
planner_llm = get_llm()
code_gen_llm = get_llm().with_structured_output(CodeGeneratorResponse)

def emit_progress(message: str):
    try:
        writer = get_stream_writer()
        writer({
            'event': 'subagent_progress',
            'tool_name': 'call_mock_generator',
            'message': message
        })
    except Exception:
        pass

# 1. Stateless Filter Node
def filter_tables_node(state: GeneratorState):
    emit_progress("Filtering relevant database tables...")
    tables = list_tables.invoke({})
    filter_prompt = (
        f"Available tables in database:\n{tables}\n\n"
        "Based on the user query, return only the list of table names relevant for generating data."
    )
    state_messages = state.get('messages', [])
    messages = [SystemMessage(content=filter_prompt)] + list(state_messages)
    
    result = filter_llm.invoke(messages)
    
    if hasattr(result, 'relevant_tables'):
        relevant_tables = result.relevant_tables
    elif isinstance(result, dict):
        relevant_tables = result.get('relevant_tables', [])
    else:
        relevant_tables = []
    
    return {'relevant_tables': relevant_tables}

# 2. Fetch Schema Node
def fetch_schema_node(state: GeneratorState):
    relevant_tables = state.get('relevant_tables', [])
    if not relevant_tables:
        return {'schema_map': ''}
    
    emit_progress(f"Fetching schema for target tables: {', '.join(relevant_tables)}...")
    schema_map = get_tables_schema_with_deps.invoke({'table_names': relevant_tables})
    return {'schema_map': schema_map}

# 3. Mock Data Generator Planner Node
def generator_planner_node(state: GeneratorState):
    emit_progress("Planning mock data generation strategy...")
    state_messages = state.get('messages', [])
    relevant_tables = state.get('relevant_tables', [])
    schema_map = state.get('schema_map', '')
    
    system_prompt = generator_planner_system_prompt
    if relevant_tables:
        system_prompt += f"\n\nRelevant tables identified for this request: {', '.join(relevant_tables)}"
    if schema_map:
        system_prompt += f"\n\nSchema map of relevant tables:\n{schema_map}"
        
    messages = [SystemMessage(content=system_prompt)] + list(state_messages)

    response = planner_llm.invoke(messages)
    return {'generated_plan': response.content}

# 4. Code Generator Node
def code_generator_node(state: GeneratorState):
    current_retries = state.get('retry_count', 0)
    emit_progress(f"Generating Python data insertion script (Attempt {current_retries + 1})...")
    state_messages = state.get('messages', [])
    schema_map = state.get('schema_map', '')
    generated_plan = state.get('generated_plan', '')
    
    system_prompt = code_generator_system_prompt
    if schema_map:
        system_prompt += f"\n\nTarget Database Schema:\n{schema_map}"
    if generated_plan:
        system_prompt += f"\n\nExecution Plan:\n{generated_plan}"
        
    prompt_messages = [SystemMessage(content=system_prompt)] + list(state_messages)
        
    response = code_gen_llm.invoke(prompt_messages)
    python_code = response.python_code
        
    return {
        'generated_code': python_code,
        'retry_count': current_retries + 1,
        'messages': [AIMessage(content=f"Generated Data Insertion Script:\n```python\n{python_code}\n```")]
    }

def _sandbox_worker(code, result_queue):
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        res = run_in_sandbox(code)
        result_queue.put(res)
    except Exception as e:
        result_queue.put((False, f"{type(e).__name__}: {str(e)}"))
    finally:
        sys.stdout = old_stdout

# 5. Sandbox Execution Node
def sandbox_execution_node(state: GeneratorState):
    emit_progress("Executing generated script in sandbox environment...")
    code = state.get('generated_code', '')
    if not code:
        emit_progress("Sandbox Execution Error: No code provided.")
        return {
            'execution_result': "No code provided to execute.",
            'execution_error': "Empty generated code."
        }

    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_sandbox_worker,
        args=(code, result_queue)
    )

    try:
        process.start()
        
        try:
            success, message = result_queue.get(timeout=15)
        except queue.Empty:
            if process.is_alive():
                process.terminate()
                error_msg = "TimeoutError: Execution timed out after 15 seconds limit."
                emit_progress("Sandbox execution timed out.")
            else:
                error_msg = "Execution failed: No result returned from process."
                emit_progress(f"Sandbox exception: {error_msg}")
                
            process.join()
                
            error_feedback = f"[Sandbox Execution Feedback]\nThe previous script execution failed with error:\n{error_msg}\nPlease analyze the error and the failed script, fix the bug, and return updated executable Python code."
            return {
                'execution_result': f"Execution failed: {error_msg}",
                'execution_error': error_msg,
                'messages': [HumanMessage(content=error_feedback)]
            }
            
        process.join()

        if success:
            emit_progress("Sandbox script execution succeeded!")
            return {
                'execution_result': message,
                'execution_error': None
            }
        else:
            emit_progress(f"Sandbox execution error: {message[:60]}...")
            error_feedback = f"[Sandbox Execution Feedback]\nThe previous script execution failed with error:\n{message}\nPlease analyze the error and the failed script, fix the bug, and return updated executable Python code."
            return {
                'execution_result': f"Execution failed: {message}",
                'execution_error': message,
                'messages': [HumanMessage(content=error_feedback)]
            }
    except Exception as e:
        # Guarantee process cleanup if an outer exception triggers
        if process.is_alive():
            process.terminate()
        process.join()

        error_msg = f"{type(e).__name__}: {str(e)}"
        emit_progress(f"Sandbox exception: {error_msg[:60]}...")
        error_feedback = f"[Sandbox Execution Feedback]\nThe previous script execution failed with error:\n{error_msg}\nPlease analyze the error and the failed script, fix the bug, and return updated executable Python code."
        return {
            'execution_result': f"Execution failed: {error_msg}",
            'execution_error': error_msg,
            'messages': [HumanMessage(content=error_feedback)]
        }

def _extract_initial_user_request(state_messages):
    for m in state_messages:
        if isinstance(m, HumanMessage):
            return m
    return None

# 6. Summary Node
def summary_node(state: GeneratorState):
    emit_progress("Generating final summary...")
    state_messages = state.get('messages', [])
    relevant_tables = state.get('relevant_tables', [])
    execution_result = state.get('execution_result', '')
    execution_error = state.get('execution_error', None)
    generated_plan = state.get('generated_plan', '')
    
    if execution_error:
        status_text = f"FAILED with error:\n{execution_error}"
    else:
        status_text = f"SUCCESS:\n{execution_result}"
        
    if generated_plan:
        status_text += f"\n\nPlanned Strategy Executed:\n{generated_plan}"
    
    summary_prompt = generator_summary_system_prompt.format(
        relevant_tables=", ".join(relevant_tables),
        status_text=status_text,
    )
    user_req = _extract_initial_user_request(state_messages)
    messages = [SystemMessage(content=summary_prompt)]
    if user_req:
        messages.append(user_req)

    response = planner_llm.invoke(messages)
    return {'messages': [response]}

# 7. Conditional Edge Router for Error Refinement
def route_execution_result(state: GeneratorState):
    execution_error = state.get('execution_error', None)
    retry_count = state.get('retry_count', 0)
    
    if execution_error and retry_count < 3:
        emit_progress(f"Execution error detected. Routing back to code generation ({retry_count}/3)...")
        return 'code_generator'
    emit_progress("Routing to summary node...")
    return 'summary'

generator_workflow = StateGraph(GeneratorState)

generator_workflow.add_node('filter_tables', filter_tables_node)
generator_workflow.add_node('fetch_schema', fetch_schema_node)
generator_workflow.add_node('planner', generator_planner_node)
generator_workflow.add_node('code_generator', code_generator_node)
generator_workflow.add_node('sandbox_execution', sandbox_execution_node)
generator_workflow.add_node('summary', summary_node)

generator_workflow.add_edge(START, 'filter_tables')
generator_workflow.add_edge('filter_tables', 'fetch_schema')
generator_workflow.add_edge('fetch_schema', 'planner')
generator_workflow.add_edge('planner', 'code_generator')
generator_workflow.add_edge('code_generator', 'sandbox_execution')

generator_workflow.add_conditional_edges(
    'sandbox_execution',
    route_execution_result,
    {
        'code_generator': 'code_generator',
        'summary': 'summary'
    }
)
generator_workflow.add_edge('summary', END)

mock_generator_graph = generator_workflow.compile(name="generator_subagent_graph")

# Subagent Tool Definition
@tool
def call_mock_generator(query: str) -> str:
    """
    Delegate mock data generation to the Mock Data Generator subagent.
    Generates and inserts mock data into database tables and returns a summary of the execution.
    
    Args:
        query: Clear request or requirements regarding mock data generation.
    """
    return "Mock Data Generator task initiated."
