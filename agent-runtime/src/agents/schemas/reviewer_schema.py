from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import logging

logger = logging.getLogger(__name__)

Severity = Literal["critical", "warning", "suggestion"]

Criterion = Literal[
    "correctness",
    "security",
    "error_handling",
    "mcp_compliance",
    "code_quality",
    "agent_safety",    
    "completeness",    
    "verbatim_drift",   
]


class ReviewIssue(BaseModel):
    severity: Severity = Field(
        description="critical forces approved=False; warning and suggestion do not."
    )
    criterion: Criterion
    description: str = Field(description="What the issue is, concretely.")
    line_hint: str | None = Field(
        default=None,
        description="Approximate location",
    )
    fix: str = Field(
        description="How to fix it. The Generator consumes this on retry, so it must be actionable on its own."
    )

    @field_validator("line_hint", mode="before")
    @classmethod
    def _coerce_line_hint(cls, v):
        """Models emit numeric line numbers constantly. Accept them."""
        return v if v is None or isinstance(v, str) else str(v)


class ReviewResult(BaseModel):
    approved: bool
    summary: str = Field(description="One sentence overall verdict.")
    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="Findings the Generator is expected to fix on the next round.",
    )
    strengths: list[str] = Field(default_factory=list)
    notes_for_human: list[str] = Field(
        default_factory=list,
        description="Findings the Generator CANNOT act on — chiefly real defects "
                    "inside verbatim blocks, which must be fixed in the source "
                    "DesignPrinciples submodel rather than in generated code. "
                    "These never affect `approved`.",
    )

    @model_validator(mode="after")
    def _critical_forces_rejection(self):
        """A critical issue ALWAYS means approved=False. The Orchestrator gates
        the build on this flag, so it cannot be left to the model's discretion.
        notes_for_human are excluded - the Generator cannot fix those."""
        if self.approved and any(i.severity == "critical" for i in self.issues):
            n = sum(1 for i in self.issues if i.severity == "critical")
            logger.warning(
                "Reviewer returned approved=True with %d critical issue(s) - forcing False", n
            )
            object.__setattr__(self, "approved", False)
            object.__setattr__(
                self, "summary", f"{self.summary} [auto-rejected: {n} critical issue(s)]"
            )
        return self

