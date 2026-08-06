from pydantic import BaseModel, Field, ConfigDict


class CodeGeneratorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    python_code: str = Field(
        description="The raw, executable Python script to generate and insert mock data into SQLite."
    )
