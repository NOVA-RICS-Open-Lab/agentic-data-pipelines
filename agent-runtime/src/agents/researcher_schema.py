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
    verbatim_functions: str = Field(
        default="",
        description="Verbatim AAS code block(s) supplied by the caller inside a "
                    "VERBATIM_FUNCTIONS section, copied through EXACTLY as given. "
                    "Never summarize, research, or alter this - it is not a research "
                    "target, just a passthrough. Empty string if the caller supplied none."
    )
    functions_to_implement: str = Field(
        default="",
        description="The FunctionsToImplement specifications supplied by the caller, "
                    "copied through EXACTLY as given, one 'Name: Purpose' per line. "
                    "Never infer, rename, merge or extend  these - it is a "
                    "passthrough. Empty string if the caller supplied none.",
    )