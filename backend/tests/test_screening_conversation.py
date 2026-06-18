"""Offline unit tests for the conversational screening agent (no DB/network).

These exercise the deterministic pieces: the turn-0 opening script, the
availability gate, and the scripted (no-LLM) one-question-at-a-time walk that
also serves as the fallback when the LLM path fails.
"""
from __future__ import annotations

from app.agents.telephonic_screening import (
    _declined_availability,
    _scripted_turn,
    next_turn,
    opening_line,
)
from app.config import settings


def test_opening_line_introduces_company_role_and_first_name():
    line = opening_line(candidate_name="Asha Verma", role="Senior Backend Engineer")
    assert settings.company_name in line  # introduces who is calling (e.g. Intelera)
    assert "Asha" in line  # confirms who we're speaking with...
    assert "Verma" not in line  # ...by first name only
    assert "Senior Backend Engineer" in line  # mentions the role
    assert "good time" in line.lower()  # asks about availability


def test_opening_line_minimal_still_intros_and_asks_availability():
    line = opening_line()
    assert settings.company_name in line
    assert "good time" in line.lower()


def test_declined_availability_detects_cues():
    assert _declined_availability("I'm a bit busy right now")
    assert _declined_availability("Can you call back later?")
    assert _declined_availability("no")
    assert _declined_availability("Not a good time, sorry")
    assert not _declined_availability("Yes, absolutely — go ahead")
    assert not _declined_availability("")


def test_scripted_turn_decline_offers_callback():
    qs = ["Q1", "Q2", "Q3"]
    d = _scripted_turn(qs, "Sorry, it's not a good time right now", 1)
    assert d.action == "end_unavailable"
    assert d.reply  # speaks a warm callback line


def test_scripted_turn_available_asks_first_question():
    qs = ["Walk me through your recent role", "Q2"]
    d = _scripted_turn(qs, "Yes, sure", 1)
    assert d.action == "continue"
    assert qs[0] in d.reply


def test_scripted_turn_walks_questions_one_at_a_time_then_completes():
    qs = ["Q1", "Q2", "Q3"]
    # turn 2 → candidate answered Q1, ask Q2; turn 3 → ask Q3
    assert qs[1] in _scripted_turn(qs, "answer to q1", 2).reply
    assert qs[2] in _scripted_turn(qs, "answer to q2", 3).reply
    # turn 4 → all questions answered → wrap up
    done = _scripted_turn(qs, "answer to q3", 4)
    assert done.action == "end_complete"


def test_next_turn_safety_cap_always_terminates():
    # Past len(questions)+3 turns the conversation is force-ended regardless of LLM.
    d = next_turn(questions=["Q1", "Q2"], transcript="…", candidate_speech="rambling", turn_index=99)
    assert d.action == "end_complete"


def test_next_turn_falls_back_to_scripted_without_llm(monkeypatch):
    from app.llm import client as llm

    monkeypatch.setattr(llm, "llm_available", lambda: False)
    qs = ["Tell me about your most recent role"]
    d = next_turn(questions=qs, transcript="Agent: …", candidate_speech="sounds good", turn_index=1)
    assert d.action == "continue"
    assert qs[0] in d.reply
