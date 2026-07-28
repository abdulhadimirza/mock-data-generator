from typing import Annotated, List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from langgraph.graph import MessagesState

class AgentState(BaseModel):
    messages: Annotated[List[AnyMessage], add_messages]
    current_agent: Optional[str] = None


class GeneratorState(MessagesState):
    relevant_tables: List[str]
    schema_map: Optional[str] = None



class TableSelectionResponse(BaseModel):
    relevant_tables: List[str] = Field(
        default_factory=list,
        description="List of table names relevant to the user query"
    )


