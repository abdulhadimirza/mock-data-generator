from unittest.mock import MagicMock, patch
from agents.generator.state import GeneratorState
from agents.generator.realistic.state import UtilityCodeResponse
from agents.generator.realistic.nodes import (
    utility_synthesizer_node,
    realistic_code_generator_node,
)
from agents.generator.realistic.graph import realistic_subgraph


def test_generator_state_response_models():
    util_resp = UtilityCodeResponse(utility_python_code="def get_date(): pass")
    assert util_resp.utility_python_code == "def get_date(): pass"


@patch("agents.generator.realistic.nodes.utility_llm")
def test_utility_synthesizer_node(mock_utility_llm):
    mock_response = MagicMock()
    mock_response.utility_python_code = "def get_random_age(): return random.randint(18, 65)"
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
    mock_response.python_code = "with get_db_connection() as conn:\n    pass"
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
    # Check that utility_code and raw loop code are prepended together
    final_code = res["generated_code"]
    assert "def get_user(): pass" in final_code
    assert "with get_db_connection() as conn:" in final_code


def test_realistic_subgraph_structure():
    node_names = set(realistic_subgraph.nodes.keys())
    expected_nodes = {
        "planner",
        "utility_synthesizer",
        "code_generator",
        "sandbox_execution",
    }
    for expected in expected_nodes:
        assert expected in node_names
