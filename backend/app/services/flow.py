"""Flow layer — durable-ish async post-response work (§4.6).

Wraps the async agent entrypoints for execution via FastAPI BackgroundTasks (and
the scheduler). A bounded semaphore caps concurrent LLM/STT work so a burst
cannot exhaust provider rate limits (§11). Each agent manages its own DB session,
so a re-trigger resumes cleanly.
"""
from __future__ import annotations

import threading
import time

from app.core.logging import get_logger, log_step

log = get_logger("flow")

# Bound concurrent heavy (LLM/STT) background jobs.
_SEM = threading.Semaphore(4)


def run_screening_processing(call_log_id: str, recording_url: str | None = None) -> None:
    from app.agents.telephonic_screening import process_call

    log.info("flow.screening.start", call_log_id=call_log_id)
    log.debug("flow.screening.sem_acquire.wait", call_log_id=call_log_id)
    _wait_start = time.perf_counter()
    with _SEM:
        log.debug("flow.screening.sem_acquire.acquired", call_log_id=call_log_id,
                  wait_ms=round((time.perf_counter() - _wait_start) * 1000, 2))
        try:
            with log_step(log, "flow.screening.process", call_log_id=call_log_id):
                process_call(call_log_id=call_log_id, recording_url=recording_url)
            log.info("screening_processed", call_log_id=call_log_id)
        except Exception as exc:
            log.error("screening_processing_failed", call_log_id=call_log_id,
                      error=str(exc), exc_info=True)


def run_interview_analysis(interview_id: str, recording_bytes: bytes | None = None,
                           recording_filename: str = "interview.mp3", recording_url: str | None = None) -> None:
    from app.agents.interview_analysis import analyze_interview

    log.info("flow.interview_analysis.start", interview_id=interview_id)
    log.debug("flow.interview_analysis.sem_acquire.wait", interview_id=interview_id)
    _wait_start = time.perf_counter()
    with _SEM:
        log.debug("flow.interview_analysis.sem_acquire.acquired", interview_id=interview_id,
                  wait_ms=round((time.perf_counter() - _wait_start) * 1000, 2))
        try:
            with log_step(log, "flow.interview_analysis.analyze", interview_id=interview_id):
                analyze_interview(interview_id=interview_id, recording_bytes=recording_bytes,
                                  recording_filename=recording_filename, recording_url=recording_url)
            log.info("interview_analyzed", interview_id=interview_id)
        except Exception as exc:
            log.error("interview_analysis_failed", interview_id=interview_id,
                      error=str(exc), exc_info=True)
