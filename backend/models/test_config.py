"""Pydantic models for test configuration."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class VariableConfig(BaseModel):
    name: str
    type: str = "String"
    value: Any = ""
    required: bool = False


class OperationConfig(BaseModel):
    name: str
    type: str = "query"  # "query" or "mutation"
    query: str = ""
    enabled: bool = True
    tps_percentage: float = 0.0
    delay_start_sec: int = 0
    variables: List[VariableConfig] = Field(default_factory=list)
    data_range_start: int = 1
    data_range_end: int = 100


class GlobalParams(BaseModel):
    name: str = ""
    description: str = ""
    host: str = ""
    platform: str = "cloud"  # "cloud" or "onprem"
    user_count: int = 10
    ramp_up_sec: int = 10
    duration_sec: int = 60
    graphql_path: str = "/graphql"
    environment_id: Optional[str] = None


class TestConfigPayload(BaseModel):
    id: Optional[str] = None
    global_params: GlobalParams = Field(default_factory=GlobalParams)
    operations: List[OperationConfig] = Field(default_factory=list)
    schema_text: str = ""
    engine: str = "locust"  # "locust" or "k6"
    debug_mode: bool = False
    cleanup_on_stop: bool = False
