from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState

class GeneratorState(MessagesState):
    generation_mode: Optional[str]
    relevant_tables: List[str]
    schema_map: Optional[str]
    generated_plan: Optional[str]
    generated_code: Optional[str]
    execution_result: Optional[str]
    execution_error: Optional[str]
    retry_count: int

class CodeGeneratorIntentResponse(BaseModel):
    generation_mode: Literal["Stress Testing", "Realistic Analytics"] = Field(
        description="The primary mode for mock data generation: 'Stress Testing' for edge-case/adversarial testing, or 'Realistic Analytics' for statistical BI and clean reporting."
    )

class TableSelectionResponse(BaseModel):
    relevant_tables: List[str] = Field(
        default_factory=list,
        description="List of table names relevant to the user query"
    )

class CodeGeneratorResponse(BaseModel):
    python_code: str = Field(
        description="The raw, executable Python script to generate and insert mock data into SQLite."
    )
