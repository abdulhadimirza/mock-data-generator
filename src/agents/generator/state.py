from typing import List, Optional
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState

class GeneratorState(MessagesState):
    relevant_tables: List[str]
    schema_map: Optional[str]
    generated_code: Optional[str]
    execution_result: Optional[str]
    execution_error: Optional[str]
    retry_count: int

class TableSelectionResponse(BaseModel):
    relevant_tables: List[str] = Field(
        default_factory=list,
        description="List of table names relevant to the user query"
    )

class CodeGeneratorResponse(BaseModel):
    python_code: str = Field(
        description="The raw, executable Python script to generate and insert mock data into SQLite."
    )
