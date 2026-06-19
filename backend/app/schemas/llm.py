"""Pydantic schemas for LLM structured outputs (used with
`with_structured_output`). Every field is optional/defaulted so model output is
robust to omissions."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------- Agent 1: resume extraction ----------
class ExtractedSkill(BaseModel):
    name: str = Field(description="Skill name as written on the resume")
    proficiency: str | None = Field(default=None, description="BEGINNER | INTERMEDIATE | EXPERT if inferable")
    years_of_experience: float | None = Field(default=None, description="Years with this skill if stated")


class ResumeExtraction(BaseModel):
    full_name: str | None = Field(default=None)
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)
    current_location: str | None = Field(default=None)
    linkedin_url: str | None = Field(default=None)
    portfolio_url: str | None = Field(default=None)
    total_experience_years: float | None = Field(default=None)
    current_company: str | None = Field(default=None)
    current_designation: str | None = Field(default=None)
    current_ctc: int | None = Field(default=None, description="Annual current CTC in INR if stated")
    expected_ctc: int | None = Field(default=None, description="Annual expected CTC in INR if stated")
    notice_period_days: int | None = Field(default=None)
    skills: list[ExtractedSkill] = Field(default_factory=list)
    summary: str = Field(default="", description="2-3 sentence professional summary of the candidate")


# ---------- Detail collection: parse a candidate's email reply ----------
class CandidateDetailsExtraction(BaseModel):
    """The logistics fields a candidate supplies by email when their resume omits
    them. All optional — populate only what the reply actually states."""

    current_ctc: int | None = Field(
        default=None, description="Annual current CTC in INR (e.g. '15 LPA' -> 1500000)")
    expected_ctc: int | None = Field(
        default=None, description="Annual expected CTC in INR (e.g. '20 LPA' -> 2000000)")
    notice_period_days: int | None = Field(
        default=None, description="Notice period in days (e.g. '2 months' -> 60, 'immediate' -> 0)")
    availability_date: str | None = Field(
        default=None, description="Earliest joining/availability date as ISO YYYY-MM-DD")
    work_mode_preference: str | None = Field(
        default=None, description="Preferred work mode: REMOTE | HYBRID | ONSITE")
    shift_preference: str | None = Field(
        default=None, description="Preferred shift: DAY | NIGHT | FLEXIBLE")


# ---------- Agent 3: live screening conversation ----------
class ConversationDirective(BaseModel):
    """One turn of the live screening call: what to say next and whether to continue."""

    reply: str = Field(default="", description="The next line the agent should speak to the candidate")
    action: str = Field(
        default="continue",
        description=(
            "continue (ask/await another answer) | end_unavailable (candidate can't talk "
            "now, offer a callback and hang up) | end_complete (screening done, thank and hang up)"
        ),
    )


# ---------- Agent 3: screening Q&A extraction ----------
class ScreeningQAItem(BaseModel):
    question: str
    answer: str = Field(default="", description="Candidate's answer extracted from the transcript")
    ai_comment: str = Field(default="", description="Brief assessment of the answer")
    ai_rating: int = Field(default=3, ge=1, le=5, description="1-5 rating of the answer")


class ScreeningEvaluation(BaseModel):
    items: list[ScreeningQAItem] = Field(default_factory=list)
    overall_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Overall screening score 0-1")
    summary: str = Field(default="")


# ---------- Agent 5: interview analysis ----------
class AnalysisQAItem(BaseModel):
    question: str
    candidate_answer: str = Field(default="")
    ai_comment: str = Field(default="")
    ai_rating: int = Field(default=3, ge=1, le=5)


class DimensionScore(BaseModel):
    score: int = Field(default=3, ge=1, le=5)
    comment: str = Field(default="")


class InterviewAnalysis(BaseModel):
    communication: DimensionScore = Field(default_factory=DimensionScore)
    technical_depth: DimensionScore = Field(default_factory=DimensionScore)
    problem_solving: DimensionScore = Field(default_factory=DimensionScore)
    culture_fit: DimensionScore = Field(default_factory=DimensionScore)
    qa_breakdown: list[AnalysisQAItem] = Field(default_factory=list)
    overall_rating: float = Field(default=0.5, ge=0.0, le=1.0, description="Overall hire-readiness 0-1")
    summary: str = Field(default="")
    strengths: str = Field(default="")
    concerns: str = Field(default="")
    recommendation: str = Field(default="MAYBE", description="STRONG_YES | YES | MAYBE | NO | STRONG_NO")
