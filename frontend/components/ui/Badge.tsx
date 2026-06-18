import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone =
  | "gray"
  | "blue"
  | "green"
  | "amber"
  | "red"
  | "purple"
  | "indigo"
  | "teal";

const toneClasses: Record<Tone, string> = {
  gray: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-blue-50 text-blue-700 ring-blue-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  purple: "bg-purple-50 text-purple-700 ring-purple-200",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  teal: "bg-teal-50 text-teal-700 ring-teal-200",
};

export function Badge({
  children,
  tone = "gray",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

// Centralised status -> tone maps so colours stay consistent across the app.
const STATUS_TONES: Record<string, Tone> = {
  // requisition
  DRAFT: "gray",
  OPEN: "green",
  ON_HOLD: "amber",
  CLOSED: "gray",
  CANCELLED: "red",
  // application
  NEW: "blue",
  SCREENING: "purple",
  SHORTLISTED: "indigo",
  INTERVIEW_SCHEDULED: "teal",
  OFFERED: "amber",
  REJECTED: "red",
  WITHDRAWN: "gray",
  HIRED: "green",
  // interview
  SCHEDULED: "blue",
  COMPLETED: "green",
  NO_SHOW: "red",
  RESCHEDULED: "amber",
  // calls
  INITIATED: "blue",
  IN_PROGRESS: "purple",
  PENDING: "amber",
  FAILED: "red",
  NO_ANSWER: "gray",
  CALLBACK_REQUESTED: "amber",
  // recommendation
  STRONG_YES: "green",
  YES: "teal",
  MAYBE: "amber",
  NO: "red",
  STRONG_NO: "red",
};

export function statusTone(status?: string | null): Tone {
  if (!status) return "gray";
  return STATUS_TONES[status.toUpperCase()] ?? "gray";
}

export function StatusBadge({
  status,
  className,
}: {
  status?: string | null;
  className?: string;
}) {
  const label = (status ?? "—").replace(/_/g, " ");
  return (
    <Badge tone={statusTone(status)} className={className}>
      {label}
    </Badge>
  );
}
