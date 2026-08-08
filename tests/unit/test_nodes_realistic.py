import os
import sys
sys.path.insert(0, os.path.abspath("src"))
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")

from unittest.mock import MagicMock, patch
from agents.generator.state import GeneratorState
from agents.generator.realistic.state import RealisticState, UtilityCodeResponse, SearchReplacePatch, SyntaxFixResponse
from agents.generator.realistic.nodes import (
    utility_synthesizer_node,
    realistic_code_generator_node,
    create_ast_checker_node,
    create_syntax_fixer_node,
)
from agents.generator.realistic.graph import realistic_subgraph, route_ast_check


def test_generator_state_response_models():
    util_resp = UtilityCodeResponse(utility_python_code="def get_date(): pass", utility_stubs_code="def get_date(): ...")
    assert util_resp.utility_python_code == "def get_date(): pass"


@patch("agents.generator.realistic.nodes.utility_llm")
def test_utility_synthesizer_node(mock_utility_llm):
    mock_response = MagicMock()
    mock_response.utility_python_code = "def get_random_age(): return random.randint(18, 65)"
    mock_response.utility_stubs_code = "def get_random_age() -> int: ..."
    mock_utility_llm.invoke.return_value = mock_response

    state: GeneratorState = {
        "schema_map": "CREATE TABLE users (id INT, age INT);",
        "generated_plan": "Generate random users",
    }
    res = utility_synthesizer_node(state)

    assert "utility_code" in res
    assert "get_random_age" in res["utility_code"]
    mock_utility_llm.invoke.assert_called_once()


@patch("agents.generator.realistic.nodes.realistic_code_llm")
def test_realistic_code_generator_node(mock_code_llm):
    mock_response = MagicMock()
    mock_response.execution_python_code = "with get_db_connection() as conn:\n    pass"
    mock_code_llm.invoke.return_value = mock_response

    state: GeneratorState = {
        "schema_map": "CREATE TABLE users (id INT);",
        "generated_plan": "Generate random users",
        "insertion_order": ["users"],
        "utility_code": "def get_user(): pass",
        "retry_count": 0,
        "messages": [],
    }
    res = realistic_code_generator_node(state)

    assert "generated_code" in res
    assert res["retry_count"] == 1
    final_code = res["generated_code"]
    assert "def get_user(): pass" in final_code
    assert "with get_db_connection() as conn:" in final_code


def test_ast_checker_node_valid_code():
    checker_node = create_ast_checker_node("utility_code")
    state: RealisticState = {
        "utility_code": "def foo():\n    return 42\n"
    }
    res = checker_node(state)
    assert res["ast_error"] is None
    assert res["ast_retry_count"] == 0


def test_ast_checker_node_invalid_code_with_line_number():
    checker_node = create_ast_checker_node("utility_code")
    # Line 1 has invalid syntax (missing colon)
    invalid_code = "def foo()\n    return 42"
    state: RealisticState = {
        "utility_code": invalid_code
    }
    res = checker_node(state)
    assert res["ast_error"] is not None
    assert "SyntaxError in utility_code at line 1" in res["ast_error"]


@patch("agents.generator.realistic.nodes.ast_fixer_llm")
def test_syntax_fixer_node_applies_patches(mock_ast_fixer_llm):
    mock_response = SyntaxFixResponse(
        patches=[
            SearchReplacePatch(search="def foo()", replace="def foo():")
        ]
    )
    mock_ast_fixer_llm.invoke.return_value = mock_response

    fixer_node = create_syntax_fixer_node("utility_code")
    state: RealisticState = {
        "utility_code": "def foo()\n    return 42",
        "ast_error": "SyntaxError in utility_code at line 1: expected ':'",
        "ast_retry_count": 0,
    }

    res = fixer_node(state)

    # Check LLM call arguments and prompt context
    mock_ast_fixer_llm.invoke.assert_called_once()
    messages = mock_ast_fixer_llm.invoke.call_args[0][0]
    human_msg_content = messages[1].content
    assert "<code_with_line_numbers>" in human_msg_content
    assert "1 | def foo()\n2 |     return 42" in human_msg_content
    assert "<syntax_error>" in human_msg_content
    assert "SyntaxError in utility_code at line 1: expected ':'" in human_msg_content

    # Check that search & replace patch was applied and retry count incremented
    assert res["utility_code"] == "def foo():\n    return 42"
    assert res["ast_retry_count"] == 1


def test_route_ast_check():
    router = route_ast_check(
        success_target="code_generator",
        fixer_target="utility_ast_fixer",
        fallback_target="utility_synthesizer",
        max_retries=3
    )

    # Case 1: No error -> proceed to success target
    state_valid: RealisticState = {"ast_error": None, "ast_retry_count": 0}
    assert router(state_valid) == "code_generator"

    # Case 2: Error present, retries = 0 -> go to fixer
    state_retry0: RealisticState = {"ast_error": "SyntaxError...", "ast_retry_count": 0}
    assert router(state_retry0) == "utility_ast_fixer"

    # Case 3: Error present, retries = 2 -> go to fixer
    state_retry2: RealisticState = {"ast_error": "SyntaxError...", "ast_retry_count": 2}
    assert router(state_retry2) == "utility_ast_fixer"

    # Case 4: Error present, retries = 3 (max) -> fallback
    state_retry3: RealisticState = {"ast_error": "SyntaxError...", "ast_retry_count": 3}
    assert router(state_retry3) == "utility_synthesizer"


def test_realistic_subgraph_structure():
    node_names = set(realistic_subgraph.nodes.keys())
    expected_nodes = {
        "planner",
        "utility_synthesizer",
        "utility_ast_checker",
        "utility_ast_fixer",
        "code_generator",
        "code_ast_checker",
        "code_ast_fixer",
        "sandbox_execution",
    }
    for expected in expected_nodes:
        assert expected in node_names
