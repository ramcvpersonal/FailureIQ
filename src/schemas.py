"""
schemas.py — Structured Output Schemas (Pydantic)
--------------------------------------------------
INTERVIEW TALKING POINT:
  Structured output forces the LLM to return valid JSON matching a schema.
  Pydantic validates the LLM's response — if the LLM returns a wrong field
  or wrong type, Pydantic catches it before it reaches your application.
  This makes LLM output reliable enough for production pipelines —
  you can feed it directly into a dashboard, ticket system, or Slack alert.
"""

from pydantic import BaseModel, Field
from typing import List, Literal


class RootCause(BaseModel):
    failure_id: str = Field(description="Identifier e.g. OOM-1 or AUTH-004")
    error_type: str = Field(description="Type of error e.g. OutOfMemoryError")
    affected_component: str = Field(description="Which component or class is affected")
    root_cause: str = Field(description="Clear explanation of why this happened")
    suggested_fix: str = Field(description="Specific actionable fix steps")
    code_fix: str = Field(default="", description="Code snippet showing the fix if applicable")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0")


class DiagnosisReport(BaseModel):
    summary: str = Field(description="One-sentence summary of what happened")
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    log_type: str = Field(description="Type of log analyzed e.g. WAS SystemOut, BVT, Javacore")
    total_failures: int = Field(ge=0)
    root_causes: List[RootCause]
    immediate_actions: List[str] = Field(description="Actions to take right now to restore service")
    prevention_recommendations: List[str] = Field(description="Long-term fixes to prevent recurrence")
