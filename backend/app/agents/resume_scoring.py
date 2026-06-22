"""Agent 2 — Resume Scoring (deterministic heuristic LangGraph, §7.2).

START → resolve_pairs → compute → persist → emit_analytics → END

Per-requisition match score (0.0–1.0) from 5 weighted dimensions:
  skills 40% · experience 20% · skill-depth 20% · location/work-mode 10% · notice 10%

Dual trigger: score a new candidate against eligible open reqs, OR score the
eligible candidate pool against a newly-created requisition.
"""
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select

from app.config import settings
from app.core.events import log_event
from app.core.logging import get_logger, log_step
from app.database.base import SessionLocal
from app.models import (
    Candidate,
    CandidateScore,
    CandidateSkill,
    JobApplication,
    Requisition,
    RequisitionSkill,
)
from app.models.enums import ApplicationStatus, EventType, RequisitionStatus, WorkMode
from app.models.logs import ApplicationStatusHistory

log = get_logger("agent.scoring")
SCORING_VERSION = "v1"

WEIGHTS = {"skills": 0.40, "experience": 0.20, "depth": 0.20, "location": 0.10, "notice": 0.10}


class ScoreState(TypedDict, total=False):
    mode: str  # "candidate" | "requisition"
    candidate_id: str | None
    requisition_id: str | None
    pairs: list[tuple[str, str]]
    computed: list[dict]


def _db(config) -> Any:
    return config["configurable"]["db"]


def resolve_pairs(state: ScoreState, config) -> dict:
    with log_step(
        log,
        "agent.scoring.resolve_pairs",
        mode=state.get("mode"),
        candidate_id=state.get("candidate_id"),
        requisition_id=state.get("requisition_id"),
    ) as step:
        db = _db(config)
        pairs: list[tuple[str, str]] = []
        if state.get("mode") == "candidate":
            cand = db.get(Candidate, uuid.UUID(state["candidate_id"]))
            if cand is None:
                log.debug("agent.scoring.candidate_not_found", candidate_id=state.get("candidate_id"))
                step["pair_count"] = 0
                return {"pairs": []}
            stmt = select(Requisition.id).where(Requisition.status == RequisitionStatus.OPEN)
            if cand.domain_id is not None:
                stmt = stmt.where(Requisition.domain_id == cand.domain_id)
            for (rid,) in db.execute(stmt).all():
                pairs.append((str(cand.id), str(rid)))
        else:  # requisition mode
            req = db.get(Requisition, uuid.UUID(state["requisition_id"]))
            if req is None:
                log.debug("agent.scoring.requisition_not_found", requisition_id=state.get("requisition_id"))
                step["pair_count"] = 0
                return {"pairs": []}
            stmt = select(Candidate.id).where(Candidate.is_blacklisted.is_(False))
            if req.domain_id is not None:
                stmt = stmt.where((Candidate.domain_id == req.domain_id) | (Candidate.domain_id.is_(None)))
            for (cid,) in db.execute(stmt).all():
                pairs.append((str(cid), str(req.id)))
        step["pair_count"] = len(pairs)
        return {"pairs": pairs}


def compute(state: ScoreState, config) -> dict:
    pairs = state.get("pairs", [])
    threshold = settings.resume_threshold_ratio
    with log_step(log, "agent.scoring.compute", pair_count=len(pairs)) as step:
        db = _db(config)
        computed: list[dict] = []
        for cid, rid in pairs:
            cand = db.get(Candidate, uuid.UUID(cid))
            req = db.get(Requisition, uuid.UUID(rid))
            if cand is None or req is None:
                continue
            s = score_pair(db, cand, req)
            log.debug(
                "agent.scoring.pair_scored",
                candidate_id=s["candidate_id"],
                requisition_id=s["requisition_id"],
                total_score=s["total_score"],
                skills_score=s["skills_score"],
                experience_score=s["experience_score"],
                skills_depth_score=s["skills_depth_score"],
                location_score=s["location_score"],
                notice_period_score=s["notice_period_score"],
                passed_ats=s["total_score"] >= threshold,
                threshold=threshold,
            )
            computed.append(s)
        passed = sum(1 for s in computed if s["total_score"] >= threshold)
        step["scored_count"] = len(computed)
        step["passed_count"] = passed
        step["threshold"] = threshold
        return {"computed": computed}


def score_pair(db, cand: Candidate, req: Requisition) -> dict:
    cand_skill_years: dict[uuid.UUID, float] = {
        cs.skill_id: (cs.years_of_experience or 0.0)
        for cs in db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == cand.id)).scalars()
    }
    req_skills = list(db.execute(select(RequisitionSkill).where(RequisitionSkill.requisition_id == req.id)).scalars())

    mandatory = [rs for rs in req_skills if rs.is_mandatory]
    if mandatory:
        matched = sum(1 for rs in mandatory if rs.skill_id in cand_skill_years)
        skills_score = matched / len(mandatory)
    else:
        skills_score = 1.0

    if req_skills:
        depth_vals = []
        for rs in req_skills:
            need = rs.minimum_years or 1.0
            have = cand_skill_years.get(rs.skill_id, 0.0)
            depth_vals.append(min(have / need, 1.0) if need else (1.0 if rs.skill_id in cand_skill_years else 0.0))
        depth_score = sum(depth_vals) / len(depth_vals)
    else:
        depth_score = 1.0

    experience_score = _experience(cand.total_experience_years, req.min_experience_years, req.max_experience_years)
    location_score = _location(cand, req)
    notice_score = _notice(cand.notice_period_days)

    total = (
        WEIGHTS["skills"] * skills_score
        + WEIGHTS["experience"] * experience_score
        + WEIGHTS["depth"] * depth_score
        + WEIGHTS["location"] * location_score
        + WEIGHTS["notice"] * notice_score
    )
    return {
        "candidate_id": str(cand.id),
        "requisition_id": str(req.id),
        "total_score": round(total, 4),
        "skills_score": round(skills_score, 4),
        "experience_score": round(experience_score, 4),
        "skills_depth_score": round(depth_score, 4),
        "location_score": round(location_score, 4),
        "notice_period_score": round(notice_score, 4),
    }


def _experience(cand_exp, min_e, max_e) -> float:
    cand_exp = cand_exp or 0.0
    if min_e is None and max_e is None:
        return 1.0
    lo, hi = (min_e or 0.0), (max_e if max_e is not None else float("inf"))
    if lo <= cand_exp <= hi:
        return 1.0
    if cand_exp < lo:
        return max(0.0, cand_exp / lo) if lo else 1.0
    return max(0.5, hi / cand_exp) if cand_exp else 0.5


def _location(cand: Candidate, req: Requisition) -> float:
    base = 0.4
    if req.work_mode == WorkMode.REMOTE:
        base = 1.0
    elif cand.work_mode_preference is not None and cand.work_mode_preference == req.work_mode:
        base = 1.0
    elif WorkMode.HYBRID in (cand.work_mode_preference, req.work_mode):
        base = 0.7
    if cand.current_location and req.location:
        cl, rl = cand.current_location.lower(), req.location.lower()
        if rl in cl or cl in rl:
            base = max(base, 0.85)
    return base


def _notice(days) -> float:
    if days is None:
        return 0.6
    if days <= 15:
        return 1.0
    if days <= 30:
        return 0.85
    if days <= 60:
        return 0.6
    if days <= 90:
        return 0.4
    return 0.2


def persist(state: ScoreState, config) -> dict:
    computed = state.get("computed", [])
    threshold = settings.resume_threshold_ratio
    with log_step(log, "agent.scoring.persist", computed_count=len(computed), threshold=threshold) as step:
        db = _db(config)
        updated = inserted = auto_linked = 0
        for s in computed:
            cid, rid = uuid.UUID(s["candidate_id"]), uuid.UUID(s["requisition_id"])
            existing = db.execute(
                select(CandidateScore).filter_by(candidate_id=cid, requisition_id=rid)
            ).scalar_one_or_none()
            if existing:
                existing.total_score = s["total_score"]
                existing.skills_score = s["skills_score"]
                existing.experience_score = s["experience_score"]
                existing.skills_depth_score = s["skills_depth_score"]
                existing.location_score = s["location_score"]
                existing.notice_period_score = s["notice_period_score"]
                existing.scoring_version = SCORING_VERSION
                updated += 1
            else:
                db.add(CandidateScore(candidate_id=cid, requisition_id=rid, scoring_version=SCORING_VERSION,
                                      total_score=s["total_score"], skills_score=s["skills_score"],
                                      experience_score=s["experience_score"], skills_depth_score=s["skills_depth_score"],
                                      location_score=s["location_score"], notice_period_score=s["notice_period_score"]))
                inserted += 1

            app = db.execute(
                select(JobApplication).filter_by(candidate_id=cid, requisition_id=rid)
            ).scalar_one_or_none()
            if app:
                app.match_score = s["total_score"]
            elif s["total_score"] >= threshold:
                # Auto-link above-threshold candidates into the requisition pipeline.
                app = JobApplication(candidate_id=cid, requisition_id=rid, status=ApplicationStatus.NEW,
                                     match_score=s["total_score"])
                db.add(app)
                db.flush()
                db.add(ApplicationStatusHistory(application_id=app.id, from_status=None,
                                                to_status=ApplicationStatus.NEW, reason_note="Auto-linked by scoring"))
                auto_linked += 1
                log.info(
                    "agent.scoring.auto_linked",
                    candidate_id=s["candidate_id"],
                    requisition_id=s["requisition_id"],
                    total_score=s["total_score"],
                )
        db.flush()
        step["scores_updated"] = updated
        step["scores_inserted"] = inserted
        step["auto_linked"] = auto_linked
        return {}


def emit_analytics(state: ScoreState, config) -> dict:
    computed = state.get("computed", [])
    with log_step(log, "agent.scoring.emit_analytics", event_count=len(computed)):
        db = _db(config)
        for s in computed:
            log_event(db, EventType.SCORE_COMPUTED,
                      candidate_id=uuid.UUID(s["candidate_id"]),
                      requisition_id=uuid.UUID(s["requisition_id"]),
                      metadata={"total_score": s["total_score"]})
        return {}


def build_scoring_graph():
    g = StateGraph(ScoreState)
    g.add_node("resolve_pairs", resolve_pairs)
    g.add_node("compute", compute)
    g.add_node("persist", persist)
    g.add_node("emit_analytics", emit_analytics)
    g.add_edge(START, "resolve_pairs")
    g.add_edge("resolve_pairs", "compute")
    g.add_edge("compute", "persist")
    g.add_edge("persist", "emit_analytics")
    g.add_edge("emit_analytics", END)
    return g.compile()


_GRAPH = build_scoring_graph()


def _run(state: ScoreState, db=None) -> int:
    own = db is None
    session = db or SessionLocal()
    try:
        with log_step(
            log,
            "agent.scoring.run",
            mode=state.get("mode"),
            candidate_id=state.get("candidate_id"),
            requisition_id=state.get("requisition_id"),
        ) as step:
            final = _GRAPH.invoke(state, config={"configurable": {"db": session}})
            count = len(final.get("computed", []))
            step["scored_count"] = count
        if own:
            session.commit()
        return count
    except Exception:
        if own:
            session.rollback()
        raise
    finally:
        if own:
            session.close()


def run_scoring_for_candidate(candidate_id: str, db=None) -> int:
    return _run({"mode": "candidate", "candidate_id": str(candidate_id)}, db=db)


def run_scoring_for_requisition(requisition_id: str, db=None) -> int:
    return _run({"mode": "requisition", "requisition_id": str(requisition_id)}, db=db)
