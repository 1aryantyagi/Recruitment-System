// Domain vocabulary → human labels, badge tones, and pipeline ordering.
// Centralizes the "premium" status styling so every surface reads consistently.

import type {
  ApplicationStatus,
  InterviewStatus,
  Recommendation,
  RequisitionStatus,
} from "./types";

type BadgeVariant =
  | "default"
  | "secondary"
  | "destructive"
  | "outline"
  | "success"
  | "warning"
  | "info"
  | "muted";

export interface StageMeta {
  key: ApplicationStatus;
  label: string;
  variant: BadgeVariant;
  /** tailwind text/bg dot color for kanban headers */
  dot: string;
  terminal?: boolean;
}

/** Ordered pipeline stages for the ATS Kanban (only persistable statuses). */
export const PIPELINE_STAGES: StageMeta[] = [
  { key: "NEW", label: "Applied", variant: "muted", dot: "bg-slate-400" },
  { key: "SCREENING", label: "Screening", variant: "info", dot: "bg-sky-500" },
  { key: "SHORTLISTED", label: "Qualified", variant: "info", dot: "bg-indigo-500" },
  {
    key: "INTERVIEW_SCHEDULED",
    label: "Interviewing",
    variant: "info",
    dot: "bg-violet-500",
  },
  { key: "OFFERED", label: "Offer", variant: "warning", dot: "bg-amber-500" },
  { key: "HIRED", label: "Hired", variant: "success", dot: "bg-emerald-500", terminal: true },
  { key: "REJECTED", label: "Rejected", variant: "destructive", dot: "bg-rose-500", terminal: true },
  { key: "WITHDRAWN", label: "Withdrawn", variant: "muted", dot: "bg-slate-400", terminal: true },
];

const STAGE_MAP: Record<ApplicationStatus, StageMeta> = PIPELINE_STAGES.reduce(
  (acc, s) => ({ ...acc, [s.key]: s }),
  {} as Record<ApplicationStatus, StageMeta>,
);

export function stageMeta(status?: ApplicationStatus | string | null): StageMeta {
  if (status && STAGE_MAP[status as ApplicationStatus]) {
    return STAGE_MAP[status as ApplicationStatus];
  }
  return { key: "NEW", label: "—", variant: "muted", dot: "bg-slate-400" };
}

export function applicationStatusVariant(
  status?: ApplicationStatus | string | null,
): BadgeVariant {
  return stageMeta(status).variant;
}

export function interviewStatusVariant(
  status?: InterviewStatus | string | null,
): BadgeVariant {
  switch (status) {
    case "SCHEDULED":
      return "info";
    case "COMPLETED":
      return "success";
    case "NO_SHOW":
      return "destructive";
    case "RESCHEDULED":
      return "warning";
    case "CANCELLED":
    default:
      return "muted";
  }
}

export function requisitionStatusVariant(
  status?: RequisitionStatus | string | null,
): BadgeVariant {
  switch (status) {
    case "OPEN":
      return "success";
    case "ON_HOLD":
      return "warning";
    case "DRAFT":
      return "muted";
    case "CLOSED":
    case "CANCELLED":
    default:
      return "secondary";
  }
}

export interface RecommendationMeta {
  label: string;
  variant: BadgeVariant;
}

export function recommendationMeta(
  rec?: Recommendation | string | null,
): RecommendationMeta {
  switch (rec) {
    case "STRONG_YES":
      return { label: "Strong Yes", variant: "success" };
    case "YES":
      return { label: "Yes", variant: "info" };
    case "MAYBE":
      return { label: "Maybe", variant: "warning" };
    case "NO":
      return { label: "No", variant: "destructive" };
    case "STRONG_NO":
      return { label: "Strong No", variant: "destructive" };
    default:
      return { label: "—", variant: "muted" };
  }
}

/** Derive a recruiter-facing recommendation from a 0–1 (or 0–100) match score. */
export function scoreRecommendation(score?: number | null): {
  label: string;
  variant: BadgeVariant;
} {
  if (score === null || score === undefined) return { label: "Unscored", variant: "muted" };
  const v = score <= 1 ? score * 100 : score;
  if (v >= 75) return { label: "Strong match", variant: "success" };
  if (v >= 60) return { label: "Good match", variant: "info" };
  if (v >= 45) return { label: "Possible", variant: "warning" };
  return { label: "Low match", variant: "destructive" };
}

/** Color class for a 0–100 score (rings, bars). */
export function scoreColor(pct: number): string {
  if (pct >= 75) return "text-emerald-500";
  if (pct >= 60) return "text-indigo-500";
  if (pct >= 45) return "text-amber-500";
  return "text-rose-500";
}
