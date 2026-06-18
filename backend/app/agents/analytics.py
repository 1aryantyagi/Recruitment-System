"""Agent 7 — Analytics (§7.7).

On-demand aggregation over the pipeline tables. Pure SQL aggregation (no LLM
required); an optional LLM digest summarizes the dashboard in natural language.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.llm import client as llm
from app.models import (
    Candidate,
    CandidateScore,
    CallLog,
    Interview,
    InterviewFeedback,
    JobApplication,
    Requisition,
)
from app.models.enums import ApplicationStatus, CallStatus, RequisitionStatus

FUNNEL_STAGES = [
    ApplicationStatus.NEW,
    ApplicationStatus.SCREENING,
    ApplicationStatus.SHORTLISTED,
    ApplicationStatus.INTERVIEW_SCHEDULED,
    ApplicationStatus.OFFERED,
    ApplicationStatus.HIRED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
]


def _status_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(JobApplication.status, func.count()).group_by(JobApplication.status)
    ).all()
    counts = {s.value: 0 for s in FUNNEL_STAGES}
    for status, n in rows:
        key = status.value if hasattr(status, "value") else str(status)
        counts[key] = int(n)
    return counts


def funnel(db: Session) -> dict[str, Any]:
    counts = _status_counts(db)
    total_apps = sum(counts.values())
    stages = [{"stage": s.value, "count": counts.get(s.value, 0)} for s in FUNNEL_STAGES]
    hired = counts.get(ApplicationStatus.HIRED.value, 0)
    # Simple stage-to-stage conversion (each stage vs total applications).
    for st in stages:
        st["conversion_rate"] = round(st["count"] / total_apps, 4) if total_apps else 0.0
    return {"stages": stages, "total_applications": total_apps,
            "hire_rate": round(hired / total_apps, 4) if total_apps else 0.0}


def sources(db: Session) -> list[dict[str, Any]]:
    hired_expr = func.sum(case((JobApplication.status == ApplicationStatus.HIRED, 1), else_=0))
    rows = db.execute(
        select(
            Candidate.source,
            func.count(func.distinct(Candidate.id)).label("candidates"),
            func.coalesce(func.avg(JobApplication.match_score), 0.0).label("avg_score"),
            func.coalesce(hired_expr, 0).label("hired"),
        )
        .select_from(Candidate)
        .outerjoin(JobApplication, JobApplication.candidate_id == Candidate.id)
        .group_by(Candidate.source)
    ).all()
    out = []
    for source, candidates, avg_score, hired in rows:
        out.append({
            "source": source.value if hasattr(source, "value") else str(source),
            "candidates": int(candidates),
            "avg_match_score": round(float(avg_score or 0.0), 4),
            "hired": int(hired or 0),
            "hire_rate": round((hired or 0) / candidates, 4) if candidates else 0.0,
        })
    return out


def open_requisition_health(db: Session) -> list[dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    reqs = db.execute(select(Requisition).where(Requisition.status == RequisitionStatus.OPEN)).scalars().all()
    out = []
    for r in reqs:
        pipeline = db.scalar(
            select(func.count()).select_from(JobApplication).where(JobApplication.requisition_id == r.id)
        )
        created = r.created_at or now
        days_open = (now - created).days if created else 0
        out.append({
            "id": str(r.id), "title": r.title, "days_open": days_open,
            "openings": r.number_of_openings, "pipeline_count": int(pipeline or 0),
        })
    return out


def time_to_hire(db: Session) -> dict[str, Any]:
    """Average days from candidate added → application HIRED."""
    rows = db.execute(
        select(JobApplication.updated_at, Candidate.created_at)
        .select_from(JobApplication)
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .where(JobApplication.status == ApplicationStatus.HIRED)
    ).all()
    durations = [(updated - created).days for updated, created in rows if updated and created]
    overall = round(sum(durations) / len(durations), 1) if durations else 0.0
    return {"overall_avg_days": overall, "hired_count": len(durations)}


def requisition_analytics(db: Session, requisition_id: str) -> dict[str, Any]:
    rid = uuid.UUID(str(requisition_id))
    req = db.get(Requisition, rid)
    if req is None:
        return {}
    status_rows = db.execute(
        select(JobApplication.status, func.count())
        .where(JobApplication.requisition_id == rid).group_by(JobApplication.status)
    ).all()
    score_rows = db.execute(
        select(CandidateScore.total_score).where(CandidateScore.requisition_id == rid)
    ).scalars().all()
    interviews = db.scalar(select(func.count()).select_from(Interview).where(Interview.requisition_id == rid))
    return {
        "requisition_id": str(rid),
        "title": req.title,
        "pipeline": {(s.value if hasattr(s, "value") else str(s)): int(n) for s, n in status_rows},
        "scored_candidates": len(score_rows),
        "avg_match_score": round(sum(score_rows) / len(score_rows), 4) if score_rows else 0.0,
        "interviews": int(interviews or 0),
    }


def dashboard(db: Session) -> dict[str, Any]:
    totals = {
        "candidates": int(db.scalar(select(func.count()).select_from(Candidate)) or 0),
        "open_requisitions": int(
            db.scalar(select(func.count()).select_from(Requisition).where(Requisition.status == RequisitionStatus.OPEN)) or 0
        ),
        "applications": int(db.scalar(select(func.count()).select_from(JobApplication)) or 0),
        "screening_calls": int(
            db.scalar(select(func.count()).select_from(CallLog).where(CallLog.status == CallStatus.COMPLETED)) or 0
        ),
        "interviews": int(db.scalar(select(func.count()).select_from(Interview)) or 0),
        "feedback_submitted": int(
            db.scalar(select(func.count()).select_from(InterviewFeedback).where(InterviewFeedback.is_submitted.is_(True))) or 0
        ),
    }
    f = funnel(db)
    return {
        "totals": totals,
        "funnel": f["stages"],
        "hire_rate": f["hire_rate"],
        "sources": sources(db),
        "open_requisitions": open_requisition_health(db),
        "time_to_hire": time_to_hire(db),
    }


def digest(db: Session) -> str:
    """Optional natural-language summary of the dashboard (short-tier LLM)."""
    data = dashboard(db)
    if not llm.llm_available():
        return "LLM digest unavailable."
    try:
        import json

        system = "Summarize the recruitment pipeline dashboard in 3-4 crisp sentences for an HR leader."
        return llm.complete_text("short", system, json.dumps(data)[:6000])
    except Exception:
        return "LLM digest unavailable."
