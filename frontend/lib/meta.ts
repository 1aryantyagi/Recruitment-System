"use client";

import { apiGet } from "./api";
import { useFetch } from "./hooks";
import type {
  Interviewer,
  NamedEntity,
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
