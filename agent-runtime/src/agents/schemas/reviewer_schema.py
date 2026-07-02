from pydantic import BaseModel, Field
from typing import Literal

class ReviewIssue(BaseModel):
    severity: Literal["critical", "warning", "suggestion"]
    criterion: Literal["correctness", "security", "error_handling", "mcp_compliance", "code_quality"]
    description: str
    line_hint: str | None = None
    fix: str

class ReviewResult(BaseModel):
    approved: bool
    summary: str = Field(description="One paragraph overall verdict")
    issues: list[ReviewIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)