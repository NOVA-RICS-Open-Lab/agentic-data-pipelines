from pydantic import BaseModel, Field
from typing import Literal

class ClientLibrary(BaseModel):
    name: str = Field(description="PyPI package name, e.g. 'confluent-kafka'")
    version: str = Field(description="Specific version, e.g. '2.5.3' — never 'latest'")
    install_command: str
    main_classes: list[str]

class Operation(BaseModel):
    name: str = Field(description="Operation name, e.g. 'produce', 'consume', 'list_topics'")
    purpose: str
    relevant_class_or_function: str

class ConnectionConfig(BaseModel):
    required_params: list[str]
    optional_params: list[str]
    example_minimal_config: dict

class TechnologyContext(BaseModel):
    technology: str
    summary: str = Field(description="2-4 sentences, technical not marketing")
    client_library: ClientLibrary
    operations: list[Operation]
    connection_config: ConnectionConfig
    minimal_working_example: str = Field(description="Python code, executable as-is")
    idioms_and_gotchas: list[str]
    sources_consulted: list[str] = Field(description="URLs the agent actually fetched")
    confidence_notes: str = Field(description="Anything uncertain, contradictory, or assumed")