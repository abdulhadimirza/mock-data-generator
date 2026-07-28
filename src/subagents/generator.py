import random
import datetime
import uuid
import sqlite3
import concurrent.futures
from contextlib import contextmanager
from faker import Faker

from typing import Optional
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from database import get_db_connection
from utils.tools import generator_tools, list_tables, get_tables_schema_with_deps
from utils.nodes import get_llm
from utils.prompts import generator_planner_system_prompt, code_generator_system_prompt
from utils.state import GeneratorState, TableSelectionResponse, CodeGeneratorResponse

# Top-level LLM Instantiation
filter_llm = get_llm().with_structured_output(TableSelectionResponse)
planner_llm = get_llm()
code_gen_llm = get_llm().with_structured_output(CodeGeneratorResponse)

# Sandbox Helper for Thread Execution & Connection Isolation
def run_in_sandbox(code: str, safe_builtins: dict):
    with get_db_connection() as conn:
        def authorizer(action_code, arg1, arg2, dbname, source):
            forbidden = {
                sqlite3.SQLITE_DELETE,
                sqlite3.SQLITE_UPDATE,
                sqlite3.SQLITE_DROP_TABLE,
                sqlite3.SQLITE_ALTER_TABLE,
                sqlite3.SQLITE_DROP_INDEX,
                sqlite3.SQLITE_DROP_TRIGGER,
                sqlite3.SQLITE_DROP_VIEW,
                sqlite3.SQLITE_DROP_VTABLE
            }
            if action_code in forbidden:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorizer)

        class SafeConn:
            def __init__(self, *args, **kwargs):
                pass

            def cursor(self):
                return conn.cursor()

            def commit(self):
                pass  # Ignore manual commits in LLM script to ensure overall transaction atomicity

            def rollback(self):
                conn.rollback()

            def close(self):
                pass  # Managed by parent context manager

            def __getattr__(self, item):
                if item.startswith("_") or item == "set_authorizer":
                    raise AttributeError(f"Access to '{item}' is restricted.")
                return getattr(conn, item)

        @contextmanager
        def safe_get_db_connection():
            yield SafeConn()

        safe_globals = {
            "__name__": "__main__",
            "__builtins__": safe_builtins,
            "sqlite3": sqlite3,
            "random": random,
            "datetime": datetime,
            "uuid": uuid,
            "Faker": Faker,
            "get_db_connection": safe_get_db_connection
        }

        local_scope = {}

        try:
            exec(code, safe_globals, local_scope)
            conn.commit()
            return True, "Successfully executed mock data insertion script in sandbox environment."
        except Exception as e:
            conn.rollback()
            return False, f"{type(e).__name__}: {str(e)}"

# 1. Stateless Filter Node
def filter_tables_node(state: GeneratorState):
    tables = list_tables.invoke({})
    filter_prompt = (
        f"Available tables in database:\n{tables}\n\n"
        "Based on the user query, return only the list of table names relevant for generating data."
    )
    state_messages = state.get("messages", [])
    messages = [SystemMessage(content=filter_prompt)] + list(state_messages)
    
    result = filter_llm.invoke(messages)
    print(result)
    
    if hasattr(result, "relevant_tables"):
        relevant_tables = result.relevant_tables
    elif isinstance(result, dict):
        relevant_tables = result.get("relevant_tables", [])
    else:
        relevant_tables = []
    
    return {"relevant_tables": relevant_tables}

# 2. Fetch Schema Node
def fetch_schema_node(state: GeneratorState):
    relevant_tables = state.get("relevant_tables", [])
    if not relevant_tables:
        return {"schema_map": ""}
    
    schema_map = get_tables_schema_with_deps.invoke({"table_names": relevant_tables})
    return {"schema_map": schema_map}

# 3. Mock Data Generator Planner Node
def generator_planner_node(state: GeneratorState):
    print("\n--- [GENERATOR PLANNER NODE] ---")
    state_messages = state.get("messages", [])
    relevant_tables = state.get("relevant_tables", [])
    schema_map = state.get("schema_map", "")
    
    system_prompt = generator_planner_system_prompt
    if relevant_tables:
        system_prompt += f"\n\nRelevant tables identified for this request: {', '.join(relevant_tables)}"
    if schema_map:
        system_prompt += f"\n\nSchema map of relevant tables:\n{schema_map}"
        
    messages = [SystemMessage(content=system_prompt)] + list(state_messages)
    response = planner_llm.invoke(messages)
    print(f"[Planner Output]:\n{response.content if hasattr(response, 'content') else response}")
    return {"messages": [response]}

# 4. Code Generator Node
def code_generator_node(state: GeneratorState):
    current_retries = state.get("retry_count", 0)
    print(f"\n--- [CODE GENERATOR NODE] (Attempt {current_retries + 1}) ---")
    state_messages = state.get("messages", [])
    schema_map = state.get("schema_map", "")
    generated_code = state.get("generated_code", None)
    execution_error = state.get("execution_error", None)
    
    system_prompt = code_generator_system_prompt
    if schema_map:
        system_prompt += f"\n\nTarget Database Schema:\n{schema_map}"
        
    prompt_messages = [SystemMessage(content=system_prompt)] + list(state_messages)
    
    if execution_error:
        print(f"[Retrying due to execution error]: {execution_error}")
        error_context = (
            f"The previous script execution failed.\n\n"
            f"FAILED SCRIPT:\n```python\n{generated_code}\n```\n\n"
            f"EXECUTION ERROR:\n{execution_error}\n\n"
            f"Please analyze the error and the failed script, fix the bug, and return updated executable Python code."
        )
        prompt_messages.append(SystemMessage(content=error_context))
        
    response = code_gen_llm.invoke(prompt_messages)
    
    if hasattr(response, "python_code"):
        python_code = response.python_code
    elif isinstance(response, dict):
        python_code = response.get("python_code", "")
    elif isinstance(response, AIMessage) or hasattr(response, "content"):
        content = str(response.content)
        if "```python" in content:
            python_code = content.split("```python")[1].split("```")[0].strip()
        elif "```" in content:
            python_code = content.split("```")[1].split("```")[0].strip()
        else:
            python_code = content.strip()
    else:
        python_code = str(response)
        
    print(f"[Generated Script]:\n{python_code}")
    
    return {
        "generated_code": python_code,
        "retry_count": current_retries + 1,
        "messages": [AIMessage(content=f"Generated Data Insertion Script:\n```python\n{python_code}\n```")]
    }

# 5. Sandbox Execution Node
def sandbox_execution_node(state: GeneratorState):
    print("\n--- [SANDBOX EXECUTION NODE] ---")
    code = state.get("generated_code", "")
    if not code:
        print("[Sandbox Execution]: No code provided to execute.")
        return {
            "execution_result": "No code provided to execute.",
            "execution_error": "Empty generated code."
        }

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        allowed_modules = {"sqlite3", "random", "datetime", "uuid", "faker", "math", "time", "decimal"}
        if name in allowed_modules:
            return __import__(name, globals, locals, fromlist, level)
        raise ImportError(f"Import of module '{name}' is forbidden in sandbox environment.")

    safe_builtins = {
        "range": range, "len": len, "str": str, "int": int, "float": float,
        "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple,
        "print": print, "enumerate": enumerate, "zip": zip, "min": min, "max": max,
        "abs": abs, "sum": sum, "any": any, "all": all, "isinstance": isinstance,
        "getattr": getattr, "hasattr": hasattr,
        "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "AttributeError": AttributeError,
        "__import__": safe_import
    }

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(run_in_sandbox, code, safe_builtins)
        success, message = future.result(timeout=15)

        if success:
            print(f"[Sandbox Execution Success]: {message}")
            return {
                "execution_result": message,
                "execution_error": None
            }
        else:
            print(f"[Sandbox Execution Error]: {message}")
            return {
                "execution_result": f"Execution failed: {message}",
                "execution_error": message
            }
    except concurrent.futures.TimeoutError:
        error_msg = "TimeoutError: Execution timed out after 15 seconds limit."
        print(f"[Sandbox Execution Timeout]: {error_msg}")
        return {
            "execution_result": f"Execution failed: {error_msg}",
            "execution_error": error_msg
        }
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[Sandbox Execution Exception]: {error_msg}")
        return {
            "execution_result": f"Execution failed: {error_msg}",
            "execution_error": error_msg
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

# 6. Summary Node
def summary_node(state: GeneratorState):
    print("\n--- [SUMMARY NODE] ---")
    state_messages = state.get("messages", [])
    relevant_tables = state.get("relevant_tables", [])
    execution_result = state.get("execution_result", "")
    
    summary_prompt = (
        f"The mock data generation run for tables {', '.join(relevant_tables)} finished with status:\n"
        f"{execution_result}\n\n"
        "Provide a clear, user-friendly, and concise summary of the data population process and results for the user. Do NOT include any Python code."
    )
    messages = [SystemMessage(content=summary_prompt)] + list(state_messages)
    response = planner_llm.invoke(messages)
    print(f"[Summary Output]:\n{response.content if hasattr(response, 'content') else response}")
    return {"messages": [response]}

# 7. Conditional Edge Router for Error Refinement
def route_execution_result(state: GeneratorState):
    execution_error = state.get("execution_error", None)
    retry_count = state.get("retry_count", 0)
    
    if execution_error and retry_count < 3:
        print(f"\n---> [ROUTER]: Execution error detected. Retrying code generation ({retry_count}/3)...")
        return "code_generator"
    print("\n---> [ROUTER]: Execution successful or max retries reached. Routing to summary node.")
    return "summary"

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

sample_generator_graph = generator_workflow.compile(name="generator_subagent_graph")


# 2. Subagent Tool Definition
@tool
def call_sample_generator(query: str) -> str:
    """
    Delegate mock data generation planning to the Sample Data Generator subagent.
    Returns a comprehensive mock data generation plan for database tables.
    
    Args:
        query: Clear request or requirements regarding mock data planning.
    """
    return "Sample Data Generator task initiated."


