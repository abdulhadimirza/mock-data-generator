from pydantic import BaseModel, Field, ConfigDict


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
