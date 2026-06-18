"""Idempotent database seed: reference data + dev accounts + sample requisitions.

Run with:  python -m scripts.seed   (from the backend/ directory, venv active)

Dev logins created:
  admin@local.dev / admin123   (ADMIN)
  hr@local.dev    / hr123      (HR)
  dm@local.dev    / dm123      (DELIVERY_MANAGER)
  alice@local.dev / int123     (interviewer)
  bob@local.dev   / int123     (interviewer)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database.base import SessionLocal
from app.models import (
    Department,
    Domain,
    PipelineStatusReason,
    Requisition,
    RequisitionSkill,
    Skill,
    SkillAlias,
    User,
)
from app.models.enums import (
    RequisitionStatus,
    SeniorityLevel,
    SkillCategory,
    UserRole,
    WorkMode,
)

DOMAINS = ["AI/ML", "DevOps", "Frontend", "Backend", "Data Science", "Cloud"]
DEPARTMENTS = ["Engineering", "Product", "Design", "Operations"]

# (canonical name, category, [aliases])
SKILLS: list[tuple[str, SkillCategory, list[str]]] = [
    ("Python", SkillCategory.PROGRAMMING_LANGUAGE, ["py", "python3", "python programming"]),
    ("JavaScript", SkillCategory.PROGRAMMING_LANGUAGE, ["js", "javascript"]),
    ("TypeScript", SkillCategory.PROGRAMMING_LANGUAGE, ["ts", "typescript"]),
    ("Java", SkillCategory.PROGRAMMING_LANGUAGE, ["java"]),
    ("Go", SkillCategory.PROGRAMMING_LANGUAGE, ["golang", "go"]),
    ("SQL", SkillCategory.DATABASE, ["sql"]),
    ("PostgreSQL", SkillCategory.DATABASE, ["postgres", "postgresql", "psql"]),
    ("MongoDB", SkillCategory.DATABASE, ["mongo", "mongodb"]),
    ("React", SkillCategory.FRAMEWORK, ["react", "reactjs", "react.js"]),
    ("Node.js", SkillCategory.FRAMEWORK, ["node", "nodejs", "node.js"]),
    ("FastAPI", SkillCategory.FRAMEWORK, ["fastapi"]),
    ("Django", SkillCategory.FRAMEWORK, ["django"]),
    ("PyTorch", SkillCategory.FRAMEWORK, ["pytorch", "torch"]),
    ("TensorFlow", SkillCategory.FRAMEWORK, ["tensorflow", "tf"]),
    ("Docker", SkillCategory.TOOL, ["docker"]),
    ("Kubernetes", SkillCategory.CLOUD, ["k8s", "kubernetes"]),
    ("AWS", SkillCategory.CLOUD, ["aws", "amazon web services"]),
    ("GCP", SkillCategory.CLOUD, ["gcp", "google cloud"]),
    ("Machine Learning", SkillCategory.DOMAIN_SKILL, ["ml", "machine learning", "ml engineer"]),
    ("Deep Learning", SkillCategory.DOMAIN_SKILL, ["dl", "deep learning"]),
    ("NLP", SkillCategory.DOMAIN_SKILL, ["nlp", "natural language processing"]),
    ("Communication", SkillCategory.SOFT_SKILL, ["communication"]),
    ("Leadership", SkillCategory.SOFT_SKILL, ["leadership"]),
]

# §9.18 — exact seed values per status category.
STATUS_REASONS: dict[str, list[str]] = {
    "DROPPED": [
        "Candidate not responding",
        "Accepted another offer",
        "Personal reasons",
        "Relocated",
        "Withdrew voluntarily",
    ],
    "L1_REJECTED": [
        "Technical skills insufficient",
        "Communication poor",
        "Attitude concerns",
        "Salary expectation mismatch",
        "No show",
    ],
    "L2_REJECTED": [
        "Deep technical gap",
        "Leadership skills lacking",
        "Culture fit concern",
        "Salary mismatch",
        "No show",
    ],
    "CLIENT_REJECTED": [
        "Profile not matching requirement",
        "Overqualified",
        "Underqualified",
        "Communication barrier",
        "Client cancelled requirement",
    ],
    "BLACKLISTED": [
        "Fraudulent information on resume",
        "Unprofessional conduct",
        "Repeated no shows",
        "Policy violation",
    ],
}

USERS = [
    ("Admin User", "admin@local.dev", UserRole.ADMIN, "admin123", False),
    ("HR User", "hr@local.dev", UserRole.HR, "hr123", False),
    ("Delivery Manager", "dm@local.dev", UserRole.DELIVERY_MANAGER, "dm123", False),
    ("Alice Interviewer", "alice@local.dev", UserRole.HR, "int123", True),
    ("Bob Interviewer", "bob@local.dev", UserRole.DELIVERY_MANAGER, "int123", True),
]


def _get_or_create(db: Session, model, defaults: dict | None = None, **filters):
    obj = db.execute(select(model).filter_by(**filters)).scalar_one_or_none()
    if obj:
        return obj, False
    obj = model(**filters, **(defaults or {}))
    db.add(obj)
    db.flush()
    return obj, True


def seed() -> None:
    db = SessionLocal()
    try:
        for name in DOMAINS:
            _get_or_create(db, Domain, name=name)
        for name in DEPARTMENTS:
            _get_or_create(db, Department, name=name)

        skill_by_name: dict[str, Skill] = {}
        for name, category, aliases in SKILLS:
            skill, _ = _get_or_create(db, Skill, defaults={"category": category, "is_verified": True}, name=name)
            skill_by_name[name] = skill
            for alias in aliases:
                _get_or_create(db, SkillAlias, defaults={"skill_id": skill.id}, alias=alias.lower())

        for status, reasons in STATUS_REASONS.items():
            for reason in reasons:
                _get_or_create(db, PipelineStatusReason, defaults={"is_active": True}, status=status, reason=reason)

        for name, email, role, pw, is_interviewer in USERS:
            _get_or_create(
                db,
                User,
                defaults={"name": name, "role": role, "password_hash": hash_password(pw), "is_interviewer": is_interviewer},
                email=email,
            )

        db.commit()

        # Sample requisitions (created by HR, owned by DM).
        hr = db.execute(select(User).filter_by(email="hr@local.dev")).scalar_one()
        dm = db.execute(select(User).filter_by(email="dm@local.dev")).scalar_one()
        eng = db.execute(select(Department).filter_by(name="Engineering")).scalar_one()
        aiml = db.execute(select(Domain).filter_by(name="AI/ML")).scalar_one()
        backend = db.execute(select(Domain).filter_by(name="Backend")).scalar_one()

        _seed_requisition(
            db, hr, dm, eng, aiml,
            title="Associate AI Engineer",
            seniority=SeniorityLevel.MID, work_mode=WorkMode.REMOTE,
            min_exp=2, max_exp=5, min_ctc=1200000, max_ctc=2200000, openings=2,
            skills=[("Python", True, 2), ("Machine Learning", True, 1), ("PyTorch", False, 1)],
            skill_by_name=skill_by_name,
            description="Build and ship ML features. Strong Python + ML fundamentals.",
        )
        _seed_requisition(
            db, hr, dm, eng, backend,
            title="Senior Backend Engineer",
            seniority=SeniorityLevel.SENIOR, work_mode=WorkMode.HYBRID,
            min_exp=5, max_exp=9, min_ctc=2500000, max_ctc=4500000, openings=1,
            skills=[("Python", True, 4), ("PostgreSQL", True, 3), ("Docker", False, 2)],
            skill_by_name=skill_by_name,
            description="Own backend services and data layer. Python + Postgres at scale.",
        )
        db.commit()
        print("Seed complete.")
    finally:
        db.close()


def _seed_requisition(db, creator, manager, dept, domain, *, title, seniority, work_mode,
                      min_exp, max_exp, min_ctc, max_ctc, openings, skills, skill_by_name, description):
    existing = db.execute(select(Requisition).filter_by(title=title)).scalar_one_or_none()
    if existing:
        return
    req = Requisition(
        title=title, description=description, domain_id=domain.id, department_id=dept.id,
        seniority_level=seniority, location="Bengaluru", work_mode=work_mode,
        min_experience_years=min_exp, max_experience_years=max_exp,
        min_budget_ctc=min_ctc, max_budget_ctc=max_ctc, number_of_openings=openings,
        status=RequisitionStatus.OPEN, created_by=creator.id, hiring_manager_id=manager.id,
    )
    db.add(req)
    db.flush()
    for sname, mandatory, years in skills:
        skill = skill_by_name.get(sname)
        if skill:
            db.add(RequisitionSkill(requisition_id=req.id, skill_id=skill.id, is_mandatory=mandatory, minimum_years=years))


if __name__ == "__main__":
    seed()
