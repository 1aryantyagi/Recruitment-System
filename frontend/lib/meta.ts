"use client";

import { apiGet } from "./api";
import { useFetch } from "./hooks";
import type {
  Interviewer,
  InterviewerSlot,
  NamedEntity,
  OpenSlot,
  RequisitionInterviewer,
  Skill,
  SkillsResponse,
  StatusReason,
} from "./types";

/** Flat list of all skills (across categories) for pickers. */
export function useSkills() {
  const { data, loading, error } = useFetch<SkillsResponse>(
    () => apiGet<SkillsResponse>("/skills"),
    [],
  );
  const byCategory = data?.by_category ?? {};
  const flat: Skill[] = Object.values(byCategory).flat();
  return { byCategory, skills: flat, loading, error };
}

export function useDomains() {
  return useFetch<NamedEntity[]>(() => apiGet<NamedEntity[]>("/domains"), []);
}

export function useDepartments() {
  return useFetch<NamedEntity[]>(
    () => apiGet<NamedEntity[]>("/departments"),
    [],
  );
}

export function useInterviewers() {
  return useFetch<Interviewer[]>(
    () => apiGet<Interviewer[]>("/interviewers"),
    [],
  );
}

/** Interviewers assigned to a requisition. */
export function useRequisitionInterviewers(requisitionId?: string) {
  return useFetch<RequisitionInterviewer[]>(
    (signal) =>
      apiGet<RequisitionInterviewer[]>(
        `/requisitions/${requisitionId}/interviewers`,
        undefined,
        signal,
      ),
    [requisitionId],
    { enabled: !!requisitionId },
  );
}

/** Recurring availability slots for one interviewer. */
export function useInterviewerSlots(interviewerId?: string) {
  return useFetch<InterviewerSlot[]>(
    (signal) =>
      apiGet<InterviewerSlot[]>(
        `/interviewers/${interviewerId}/slots`,
        undefined,
        signal,
      ),
    [interviewerId],
    { enabled: !!interviewerId },
  );
}

/** Open (free) interview slots a requisition can be booked into. */
export function useOpenSlots(requisitionId?: string) {
  return useFetch<OpenSlot[]>(
    (signal) =>
      apiGet<OpenSlot[]>(
        `/requisitions/${requisitionId}/open-slots`,
        undefined,
        signal,
      ),
    [requisitionId],
    { enabled: !!requisitionId },
  );
}

export function useStatusReasons(status?: string) {
  return useFetch<StatusReason[]>(
    () =>
      apiGet<StatusReason[]>(
        "/status-reasons",
        status ? { status } : undefined,
      ),
    [status],
  );
}
