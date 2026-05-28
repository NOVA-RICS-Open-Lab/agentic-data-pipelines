from pydantic import BaseModel, Field


class GeneratedTool(BaseModel):
    name: str = Field(
        description="Tool function name, snake_case. E.g. 'create_topic', 'list_topics'."
    )
    params_signature: str = Field(
        description="Parameter list as it appears in def, e.g. 'topic: str, num_partitions: int = 1'. "
                    "Empty string if no params."
    )
    return_type: str = Field(
        description="Return type annotation as a string, e.g. 'dict' or 'list[dict]'."
    )
    docstring: str = Field(
        description="Multi-line docstring content without surrounding triple quotes. "
                    "Should describe what the tool does, its parameters, and what it returns."
    )
    body: str = Field(
        description="Function body as Python code, written unindented (template handles indentation). "
                    "Use real library methods only — never invent function names."
    )


class HelperFunction(BaseModel):
    name: str = Field(description="Helper function name, typically prefixed with underscore.")
    code: str = Field(
        description="Complete function definition starting with 'def' or 'async def'. "
                    "Must be unindented (at module level)."
    )


class GenerationPlan(BaseModel):
    technology_lower: str = Field(
        description="Lowercase technology name used in filenames and identifiers, e.g. 'kafka'."
    )
    technology_pascal: str = Field(
        description="PascalCase or readable name used in logging messages, e.g. 'Kafka'."
    )
    default_port: int = Field(
        description="Port the MCP server will listen on in HTTP mode, e.g. 8093."
    )
    server_instructions: str = Field(
        description="The multi-line docstring describing what the MCP server does. "
                    "Should list available tool groups and any important usage notes."
    )
    extra_imports: list[str] = Field(
        default_factory=list,
        description="Additional imports beyond the standard ones. "
                    "E.g. ['import json', 'import httpx', 'from confluent_kafka import AdminClient']."
    )
    module_constants: list[str] = Field(
        default_factory=list,
        description="Module-level constants, one per string, including the assignment. "
                    "E.g. ['BOOTSTRAP_SERVERS = os.environ.get(\"KAFKA_BOOTSTRAP_SERVERS\", \"broker:9092\")']."
    )
    helper_functions: list[HelperFunction] = Field(
        default_factory=list,
        description="Optional helper functions placed at the top of the server file, before the tools."
    )
    tools: list[GeneratedTool] = Field(
        description="MCP tools to expose. Aim for the operations the SystemAgent needs to use this "
                    "technology in pipelines, not every method the library offers."
    )
    clarification_questions: list[str] = Field(
        default_factory=list,
        description="Specific, targeted questions for the Researcher. Populate this ONLY if you "
                    "encounter a gap in the TechnologyContext that genuinely blocks you from "
                    "writing a working tool (e.g., missing authentication headers, unknown "
                    "pagination syntax). If populated, the Orchestrator will pause generation, "
                    "get answers, and call you again."
    )
    uncertainties: list[str] = Field(
        default_factory=list,
        description="Anything the agent was unsure about, couldn't verify, or had to assume."
    )