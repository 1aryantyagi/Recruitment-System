"""ORM → dict serializers for API responses.

Enforces REQ-DP-9: sensitive fields (phone, current_ctc, expected_ctc) are
excluded from list serialization and included only in the single-profile view.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.storage import local as storage
from app.models import (
    Candidate,
    CandidateResume,
    CandidateScore,
    CandidateSkill,
    CallLog,
    Department,
    Domain,
    Interview,
    InterviewFeedback,
    JobApplication,
    PipelineStatusReason,
    Requisition,
    RequisitionSkill,
    Skill,
    User,
)


def _enum(v):
    return v.value if hasattr(v, "value") else v


def _iso(v):
    return v.isoformat() if v else None


def user_public(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": str(u.id), "name": u.name, "email": u.email, "role": _enum(u.role),
            "is_interviewer": u.is_interviewer, "is_active": u.is_active}


def skill_dict(s: Skill) -> dict:
    return {"id": str(s.id), "name": s.name, "category": _enum(s.category), "is_verified": s.is_verified}


def status_reason_dict(r: PipelineStatusReason) -> dict:
    return {"id": str(r.id), "status": r.status, "reason": r.reason, "is_active": r.is_active}


def candidate_skill_dict(cs: CandidateSkill) -> dict:
    return {
        "id": str(cs.id),
        "skill_id": str(cs.skill_id),
        "skill_name": cs.skill.name if cs.skill else None,
        "category": _enum(cs.skill.category) if cs.skill else None,
        "proficiency_level": _enum(cs.proficiency_level),
        "years_of_experience": cs.years_of_experience,
        "is_verified": cs.is_verified,
    }


def resume_dict(r: CandidateResume, include_url: bool = True) -> dict:
    d = {
        "id": str(r.id),
        "is_latest": r.is_latest,
        "uploaded_at": _iso(r.uploaded_at),
        "gmail_message_id": r.gmail_message_id,
        "has_file": bool(r.file_url),
    }
    if include_url and r.file_url:
        d["file_url"] = storage.signed_url(r.file_url)
    return d


def candidate_list_item(c: Candidate) -> dict:
    """List view — excludes encrypted fields (§4.9)."""
    return {
        "id": str(c.id),
        "full_name": c.full_name,
        "email": c.email,
        "current_location": c.current_location,
        "domain": c.domain.name if c.domain else None,
        "total_experience_years": c.total_experience_years,
        "current_company": c.current_company,
        "current_designation": c.current_designation,
        "notice_period_days": c.notice_period_days,
        "work_mode_preference": _enum(c.work_mode_preference),
        "source": _enum(c.source),
        "ai_summary": c.ai_summary,
        "is_blacklisted": c.is_blacklisted,
        "created_at": _iso(c.created_at),
    }


def candidate_detail(db: Session, c: Candidate) -> dict:
    """Full profile — includes decrypted sensitive fields (§4.9)."""
    base = candidate_list_item(c)
    base.update({
        "phone": c.phone,  # decrypted by the EncryptedString type
        "current_ctc": c.current_ctc,
        "expected_ctc": c.expected_ctc,
        "linkedin_url": c.linkedin_url,
        "portfolio_url": c.portfolio_url,
        "availability_date": _iso(c.availability_date),
        "shift_preference": _enum(c.shift_preference),
        "source_detail": c.source_detail,
        "custom_metadata": c.custom_metadata or {},
        "blacklist_note": c.blacklist_note,
        "blacklisted_at": _iso(c.blacklisted_at),
        "skills": [candidate_skill_dict(cs) for cs in db.execute(
            select(CandidateSkill).where(CandidateSkill.candidate_id == c.id)).scalars()],
        "resumes": [resume_dict(r) for r in db.execute(
            select(CandidateResume).where(CandidateResume.candidate_id == c.id)
            .order_by(CandidateResume.uploaded_at.desc())).scalars()],
        "scores": [score_dict(s) for s in db.execute(
            select(CandidateScore).where(CandidateScore.candidate_id == c.id)).scalars()],
        "applications": [application_dict(a) for a in db.execute(
            select(JobApplication).where(JobApplication.candidate_id == c.id)).scalars()],
        "calls": [call_dict(cl) for cl in db.execute(
            select(CallLog).where(CallLog.candidate_id == c.id).order_by(CallLog.called_at.desc())).scalars()],
        "interviews": [interview_dict(i, with_feedback=True, db=db) for i in db.execute(
            select(Interview).where(Interview.candidate_id == c.id).order_by(Interview.round_number)).scalars()],
    })
    return base


def score_dict(s: CandidateScore) -> dict:
    return {
        "requisition_id": str(s.requisition_id),
        "total_score": s.total_score,
        "skills_score": s.skills_score,
        "experience_score": s.experience_score,
        "skills_depth_score": s.skills_depth_score,
        "location_score": s.location_score,
        "notice_period_score": s.notice_period_score,
        "scoring_version": s.scoring_version,
    }


def application_dict(a: JobApplication) -> dict:
    return {
        "id": str(a.id),
        "candidate_id": str(a.candidate_id),
        "requisition_id": str(a.requisition_id),
        "status": _enum(a.status),
        "match_score": a.match_score,
        "rejection_reason": a.rejection_reason,
        "notes": a.notes,
        "created_at": _iso(a.created_at),
        "updated_at": _iso(a.updated_at),
    }


def requisition_skill_dict(rs: RequisitionSkill) -> dict:
    return {
        "skill_id": str(rs.skill_id),
        "skill_name": rs.skill.name if rs.skill else None,
        "is_mandatory": rs.is_mandatory,
        "minimum_years": rs.minimum_years,
    }


def requisition_dict(db: Session, r: Requisition, detail: bool = False) -> dict:
    d = {
        "id": str(r.id),
        "title": r.title,
        "domain": r.domain.name if r.domain else None,
        "department": r.department.name if r.department else None,
        "seniority_level": _enum(r.seniority_level),
        "location": r.location,
        "work_mode": _enum(r.work_mode),
        "min_experience_years": r.min_experience_years,
        "max_experience_years": r.max_experience_years,
        "number_of_openings": r.number_of_openings,
        "status": _enum(r.status),
        "created_at": _iso(r.created_at),
    }
    if detail:
        d.update({
            "description": r.description,
            "shift_timing": _enum(r.shift_timing),
            "min_budget_ctc": r.min_budget_ctc,
            "max_budget_ctc": r.max_budget_ctc,
            "target_close_date": _iso(r.target_close_date),
            "skills": [requisition_skill_dict(rs) for rs in db.execute(
                select(RequisitionSkill).where(RequisitionSkill.requisition_id == r.id)).scalars()],
            "pipeline_count": int(db.scalar(
                select(__import__("sqlalchemy").func.count()).select_from(JobApplication)
                .where(JobApplication.requisition_id == r.id)) or 0),
        })
    return d


def call_dict(c: CallLog) -> dict:
    return {
        "id": str(c.id),
        "candidate_id": str(c.candidate_id),
        "requisition_id": str(c.requisition_id) if c.requisition_id else None,
        "status": _enum(c.status),
        "twilio_call_sid": c.twilio_call_sid,
        "ai_score": c.ai_score,
        "transcript": c.transcript,
        "screening_answers": c.screening_answers,
        "question_set": c.question_set,
        "called_at": _iso(c.called_at),
        "completed_at": _iso(c.completed_at),
    }


def feedback_dict(f: InterviewFeedback | None) -> dict | None:
    if f is None:
        return None
    return {
        "id": str(f.id),
        "ai_summary": f.ai_summary,
        "ai_strengths": f.ai_strengths,
        "ai_concerns": f.ai_concerns,
        "ai_qa_breakdown": f.ai_qa_breakdown,
        "human_summary": f.human_summary,
        "human_strengths": f.human_strengths,
        "human_concerns": f.human_concerns,
        "technical_rating": f.technical_rating,
        "communication_rating": f.communication_rating,
        "problem_solving_rating": f.problem_solving_rating,
        "culture_fit_rating": f.culture_fit_rating,
        "overall_rating": f.overall_rating,
        "recommendation": _enum(f.recommendation),
        "is_submitted": f.is_submitted,
        "submitted_at": _iso(f.submitted_at),
        "last_updated_at": _iso(f.last_updated_at),
    }


def interview_dict(i: Interview, with_feedback: bool = False, db: Session | None = None) -> dict:
    d = {
        "id": str(i.id),
        "candidate_id": str(i.candidate_id),
        "requisition_id": str(i.requisition_id) if i.requisition_id else None,
        "interviewer": user_public(i.interviewer) if i.interviewer_id else None,
        "round_number": i.round_number,
        "round_type": _enum(i.round_type),
        "status": _enum(i.status),
        "scheduled_at": _iso(i.scheduled_at),
        "meeting_link": i.meeting_link,
        "calendar_event_id": i.calendar_event_id,
        "ai_overall_rating": i.ai_overall_rating,
        "ai_analysis": i.ai_analysis,
        "has_recording": bool(i.recording_url),
        "analysis_completed_at": _iso(i.analysis_completed_at),
    }
    if with_feedback:
        d["feedback"] = feedback_dict(i.feedback)
    return d


def domain_dict(d: Domain) -> dict:
    return {"id": str(d.id), "name": d.name}


def department_dict(d: Department) -> dict:
    return {"id": str(d.id), "name": d.name}
