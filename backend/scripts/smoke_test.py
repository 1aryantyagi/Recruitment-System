"""End-to-end smoke test against a running server (default http://127.0.0.1:8000).

Exercises the full pipeline: login → upload resume → skills → scoring →
screening → schedule → recording/analysis → feedback → analytics, plus RBAC and
dedup checks. Run with the server already up:  python -m scripts.smoke_test
"""
from __future__ import annotations

import io
import os
import sys
import time

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8000")


def _docx(text: str) -> bytes:
    import docx

    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _resume(email: str) -> str:
    return f"""John Doe
Email: {email}
Phone: +91 9876543210
Location: Bengaluru
Senior Python Engineer with 6 years of experience.
Skills: Python, PostgreSQL, Docker, Machine Learning, FastAPI.
Current company: Acme Corp. Current designation: Senior Engineer.
Notice period: 30 days. Expected CTC: 3500000.
"""


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def wait_for_health(client: httpx.Client, tries: int = 30) -> None:
    for _ in range(tries):
        try:
            r = client.get(f"{BASE}/health", timeout=2)
            if r.status_code == 200:
                print("health:", r.json())
                return
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit("server did not become healthy")


def check(label: str, ok: bool, extra: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {extra}" if extra else ""))
    if not ok:
        check.failures += 1  # type: ignore


check.failures = 0  # type: ignore


def _poll(fn, predicate, timeout: int = 60, interval: float = 2.0):
    deadline = time.time() + timeout
    val = fn()
    while time.time() < deadline:
        if predicate(val):
            return val
        time.sleep(interval)
        val = fn()
    return val


def main() -> int:
    c = httpx.Client(timeout=60)
    wait_for_health(c)

    # 1. Login (HR + DM)
    r = c.post(f"{BASE}/auth/login", json={"email": "hr@local.dev", "password": "hr123"})
    check("HR login", r.status_code == 200, str(r.status_code))
    hr = r.json()["data"]["access_token"]
    H = {"Authorization": f"Bearer {hr}"}

    r = c.post(f"{BASE}/auth/login", json={"email": "dm@local.dev", "password": "dm123"})
    dm = r.json()["data"]["access_token"]
    D = {"Authorization": f"Bearer {dm}"}

    r = c.post(f"{BASE}/auth/login", json={"email": "hr@local.dev", "password": "wrong"})
    check("Bad password rejected", r.status_code == 401, str(r.status_code))

    # 2. List requisitions (seeded)
    r = c.get(f"{BASE}/requisitions", headers=H)
    reqs = r.json()["data"]
    check("List requisitions", r.status_code == 200 and len(reqs) >= 2, f"{len(reqs)} reqs")
    req_id = reqs[0]["id"]

    # 3. Upload a resume (unique email per run for deterministic dedup)
    run_email = f"john.doe+{int(time.time())}@example.com"
    data = _docx(_resume(run_email))
    files = [("files", ("john_doe.docx", data, _DOCX_MIME))]
    r = c.post(f"{BASE}/candidates", headers=H, files=files, data={"email": run_email})
    check("Upload resume", r.status_code == 200, str(r.status_code))
    results = r.json()["data"]["results"]
    cand_id = results[0].get("candidate_id")
    check("Candidate created", bool(cand_id), str(results[0]))
    print("    ai_summary:", (results[0].get("ai_summary") or "")[:80])

    # 3b. DM cannot upload (RBAC)
    r = c.post(f"{BASE}/candidates", headers=D, files=[("files", ("x.docx", data, _DOCX_MIME))])
    check("DM upload forbidden (RBAC)", r.status_code == 403, str(r.status_code))

    # 3c. Duplicate email -> DUPLICATE_CANDIDATE
    r = c.post(f"{BASE}/candidates", headers=H, files=[("files", ("dup.docx", data, _DOCX_MIME))],
               data={"email": run_email})
    dup_results = r.json()["data"]["results"]
    check("Duplicate email handled", any(x.get("error") == "DUPLICATE_CANDIDATE" for x in dup_results), str(dup_results))

    # 4. Candidate list excludes encrypted fields
    r = c.get(f"{BASE}/candidates", headers=H)
    listing = r.json()
    item = next((x for x in listing["data"] if x["id"] == cand_id), None)
    check("List envelope shape", all(k in listing for k in ("data", "total", "page", "limit", "total_pages")))
    check("List excludes phone/CTC", item is not None and "phone" not in item and "current_ctc" not in item)

    # 4b. Detail includes decrypted fields
    r = c.get(f"{BASE}/candidates/{cand_id}", headers=H)
    detail = r.json()["data"]
    check("Detail has phone field", "phone" in detail and "current_ctc" in detail)
    skills = detail.get("skills", [])
    print("    extracted skills:", [s["skill_name"] for s in skills])

    # 5. Confirm a skill (if any)
    if skills:
        r = c.post(f"{BASE}/candidates/{cand_id}/confirm-skills", headers=H,
                   json={"confirmed_skill_ids": [skills[0]["skill_id"]], "added_skill_names": ["GraphQL"]})
        check("Confirm skills", r.status_code == 200, str(r.status_code))

    # 6. Scoring populated candidate_scores (ranked candidates for a req)
    r = c.get(f"{BASE}/requisitions/{req_id}/candidates", headers=H)
    ranked = r.json()["data"]
    check("Requisition candidates ranked", r.status_code == 200, f"{len(ranked)} scored")

    # 7. Screening (mock auto-completes in background; LLM eval may take ~10-30s)
    r = c.post(f"{BASE}/screening/start-call", headers=H, json={"candidate_id": cand_id, "requisition_id": req_id})
    check("Start screening call", r.status_code == 200, str(r.json().get("data", {}).get("mock")))
    # Second concurrent call -> ACTIVE_CALL_EXISTS
    r2 = c.post(f"{BASE}/screening/start-call", headers=H, json={"candidate_id": cand_id, "requisition_id": req_id})
    check("Active call guard", r2.status_code == 409 and r2.json()["error"]["code"] == "ACTIVE_CALL_EXISTS", str(r2.status_code))
    calls = _poll(lambda: c.get(f"{BASE}/screening/{cand_id}/calls", headers=H).json()["data"],
                  lambda v: bool(v) and v[0]["status"] == "COMPLETED", timeout=60)
    check("Call processed (async)", calls and calls[0]["status"] == "COMPLETED",
          f"status={calls[0]['status'] if calls else 'none'} ai_score={calls[0].get('ai_score') if calls else None}")

    # 8. Schedule interview
    r = c.get(f"{BASE}/interviewers", headers=H)
    interviewers = r.json()["data"]
    interviewer_id = interviewers[0]["id"] if interviewers else None
    r = c.post(f"{BASE}/interviews", headers=H, json={
        "candidate_id": cand_id, "requisition_id": req_id, "interviewer_id": interviewer_id,
        "round_type": "L1", "scheduled_at": "2026-07-01T10:00:00Z"})
    check("Schedule interview", r.status_code == 200, str(r.status_code))
    interview_id = r.json()["data"]["id"]

    # 9. Upload recording -> 202 -> AI analysis (background, ~10-30s) -> Agent 6 chain
    r = c.post(f"{BASE}/interviews/{interview_id}/recording", headers=H,
               files=[("file", ("rec.mp3", b"\x00\x01\x02mockaudio", "audio/mpeg"))])
    check("Recording accepted (202)", r.status_code == 202, str(r.status_code))
    fb_view = _poll(lambda: c.get(f"{BASE}/interviews/{interview_id}/feedback", headers=H).json()["data"],
                    lambda v: v.get("ai_overall_rating") is not None, timeout=60)
    check("AI interview analysis (async)", fb_view.get("ai_overall_rating") is not None,
          f"ai_rating={fb_view.get('ai_overall_rating')}")

    # 10. Submit human feedback (combined with AI analysis)
    r = c.post(f"{BASE}/interviews/{interview_id}/feedback", headers=H, json={
        "human_summary": "Solid candidate", "technical_rating": 4, "communication_rating": 4,
        "problem_solving_rating": 4, "culture_fit_rating": 5, "overall_rating": 4, "recommendation": "YES"})
    check("Submit feedback", r.status_code == 200, str(r.status_code))
    r = c.get(f"{BASE}/interviews/{interview_id}/feedback", headers=H)
    fb = r.json()["data"]
    check("Feedback combined view", fb.get("feedback", {}).get("recommendation") == "YES",
          f"ai_rating={fb.get('ai_overall_rating')}")

    # 11. Analytics
    r = c.get(f"{BASE}/analytics/dashboard", headers=H)
    dash = r.json()["data"]
    check("Analytics dashboard", r.status_code == 200 and "funnel" in dash,
          f"candidates={dash['totals']['candidates']}")
    r = c.get(f"{BASE}/analytics/funnel", headers=D)  # DM can view analytics
    check("DM can view analytics", r.status_code == 200)

    # 12. Pagination clamp
    r = c.get(f"{BASE}/candidates?limit=999", headers=H)
    check("Pagination clamps limit<=100", r.json()["limit"] <= 100, str(r.json()["limit"]))

    print(f"\n=== {'ALL PASSED' if check.failures == 0 else str(check.failures) + ' FAILURES'} ===")
    return 1 if check.failures else 0


if __name__ == "__main__":
    sys.exit(main())
