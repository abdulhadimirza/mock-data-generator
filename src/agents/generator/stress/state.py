from pydantic import BaseModel, Field, ConfigDict

from ..state import GeneratorState


class StressState(GeneratorState):
    pass


class CodeGeneratorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    python_code: str = Field(
        description="The raw, executable Python script to generate and insert mock data into SQLite."
    )
