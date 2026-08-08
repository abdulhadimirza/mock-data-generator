from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from ..state import GeneratorState


class RealisticState(GeneratorState):
    utility_code: Optional[str]
    utility_stubs_code: Optional[str]
    ast_error: Optional[str]
    ast_retry_count: Optional[int]


class SearchReplacePatch(BaseModel):
    search: str = Field(description="The exact snippet of raw code containing the syntax error to be replaced.")
    replace: str = Field(description="The corrected raw code snippet.")


class SyntaxFixResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patches: list[SearchReplacePatch] = Field(description="List of search and replace operations to fix syntax errors.")


class UtilityCodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utility_python_code: str = Field(
        description=(
            "Complete, executable Python code implementing helper functions "
            "for realistic data generation (e.g., distribution sampling, "
            "localized Faker logic, stateful unique containers, domain formulas)."
        )
    )
    utility_stubs_code: str = Field(
        description=(
            "Lean .pyi type stub signatures for all helper functions in "
            "utility_python_code. Must include explicit type hints, concise "
            "docstrings, and function declarations without implementations."
        )
    )


class CodeGeneratorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_python_code: str = Field(
        description="Executable Python code to generate database records using memory-safe batching and foreign key streaming. Assumes prepended helper functions."
    )
