"""Pydantic request models for the API layer (Zod-equivalent validation)."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MsSsoLoginRequest(BaseModel):
    ms_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    # Optional: when supplied, the refresh token is revoked server-side so it
    # can never be rotated again. Absent → best-effort stateless logout.
    refresh_token: str | None = None


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    role: str = Field(description="HR | DELIVERY_MANAGER | ADMIN")
    password: str = Field(min_length=4)
    is_interviewer: bool = False


class RequisitionSkillInput(BaseModel):
    skill_id: str | None = None
    skill_name: str | None = None
    is_mandatory: bool = True
    minimum_years: float | None = None


class CreateRequisitionRequest(BaseModel):
    title: str
    description: str | None = None
    domain_id: str | None = None
    department_id: str | None = None
    seniority_level: str | None = None
    location: str | None = None
    work_mode: str | None = None
    shift_timing: str | None = None
    min_experience_years: float | None = None
    max_experience_years: float | None = None
    min_budget_ctc: int | None = None
    max_budget_ctc: int | None = None
    number_of_openings: int = 1
    hiring_manager_id: str | None = None
    target_close_date: str | None = None
    skills: list[RequisitionSkillInput] = Field(default_factory=list)


class UpdateRequisitionRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    location: str | None = None
    work_mode: str | None = None
    min_experience_years: float | None = None
    max_experience_years: float | None = None
    min_budget_ctc: int | None = None
    max_budget_ctc: int | None = None
    number_of_openings: int | None = None
    hiring_manager_id: str | None = None
    target_close_date: str | None = None


class UpdateCandidateRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    current_location: str | None = None
    current_company: str | None = None
    current_designation: str | None = None
    current_ctc: int | None = None
    expected_ctc: int | None = None
    notice_period_days: int | None = None
    work_mode_preference: str | None = None
    domain_id: str | None = None
    custom_metadata: dict | None = None


class ConfirmSkillsRequest(BaseModel):
    confirmed_skill_ids: list[str] = Field(default_factory=list)
    removed_skill_ids: list[str] = Field(default_factory=list)
    added_skill_names: list[str] = Field(default_factory=list)


class CreateSkillRequest(BaseModel):
    name: str
    category: str = "TOOL"


class AddAliasRequest(BaseModel):
    aliases: list[str]


class StartCallRequest(BaseModel):
    candidate_id: str
    requisition_id: str | None = None
    question_set_id: str | None = None


class ScheduleInterviewRequest(BaseModel):
    candidate_id: str
    requisition_id: str | None = None
    interviewer_id: str | None = None
    round_type: str
    scheduled_at: str | None = None
    meeting_link: str | None = None


class UpdateInterviewRequest(BaseModel):
    status: str


class AssignInterviewerRequest(BaseModel):
    interviewer_id: str


class InterviewerSlotRequest(BaseModel):
    slot_time: str = Field(description="Local time-of-day, 'HH:MM' (e.g. '16:30')")
    weekday_mask: int = Field(default=0b0011111, ge=0, le=0b1111111,
                              description="Bitmask of weekdays (Mon=bit0 … Sun=bit6); default Mon–Fri")
    duration_minutes: int = Field(default=60, ge=15, le=240)


class UpdateInterviewerSlotRequest(BaseModel):
    slot_time: str | None = None
    weekday_mask: int | None = Field(default=None, ge=0, le=0b1111111)
    duration_minutes: int | None = Field(default=None, ge=15, le=240)
    is_active: bool | None = None


class FeedbackRequest(BaseModel):
    human_summary: str | None = None
    human_strengths: str | None = None
    human_concerns: str | None = None
    technical_rating: int | None = Field(default=None, ge=1, le=5)
    communication_rating: int | None = Field(default=None, ge=1, le=5)
    problem_solving_rating: int | None = Field(default=None, ge=1, le=5)
    culture_fit_rating: int | None = Field(default=None, ge=1, le=5)
    overall_rating: int | None = Field(default=None, ge=1, le=5)
    recommendation: str | None = None
    is_submitted: bool = True


class BlacklistRequest(BaseModel):
    reason_id: str | None = None
    note: str | None = None


class CreateTeamsMappingRequest(BaseModel):
    """Admin: map a hiring domain to its Microsoft Teams group/channel."""

    domain_id: str
    teams_group_name: str
    teams_team_id: str
    teams_channel_id: str
    is_active: bool = True


class UpdateTeamsMappingRequest(BaseModel):
    teams_group_name: str | None = None
    teams_team_id: str | None = None
    teams_channel_id: str | None = None
    is_active: bool | None = None


class CreateApplicationRequest(BaseModel):
    candidate_id: str
    requisition_id: str


class UpdateApplicationStatusRequest(BaseModel):
    """Move a pipeline application to a new stage (Kanban drag-and-drop)."""

    status: str = Field(description="Target ApplicationStatus, e.g. NEW | SCREENING | …")
    reason_id: str | None = None
    reason_note: str | None = None
