"use client";

import {
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock,
  FileSearch,
  Phone,
  Users,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn, formatDate, scoreToPercent } from "@/lib/utils";
import type { CandidateDetail } from "@/lib/types";

/**
 * Per-role hiring pipeline for one requisition: the status of each stage the
 * candidate moves through — Resume ATS → Telephonic → L1 → L2 — derived from the
 * candidate's score, application status, screening calls, and interviews for
 * that role. This complements the single "current status" badge by showing where
 * the candidate stands at every step.
 */

type StepState = "passed" | "completed" | "current" | "rejected" | "upcoming";

type BadgeVariant = "success" | "info" | "warning" | "destructive" | "muted";

const STATE_META: Record<
  StepState,
  { variant: BadgeVariant; label: string; Icon: LucideIcon; iconColor: string }
> = {
  passed: { variant: "success", label: "Passed", Icon: CheckCircle2, iconColor: "text-emerald-500" },
  completed: { variant: "info", label: "Completed", Icon: CheckCircle2, iconColor: "text-primary" },
  current: { variant: "warning", label: "In progress", Icon: Clock, iconColor: "text-amber-500" },
  rejected: { variant: "destructive", label: "Did not clear", Icon: XCircle, iconColor: "text-destructive" },
  upcoming: { variant: "muted", label: "Upcoming", Icon: Circle, iconColor: "text-muted-foreground/50" },
};

// Linear rank of the forward-moving application statuses.
const RANK: Record<string, number> = {
  NEW: 0,
  SCREENING: 1,
  SHORTLISTED: 2,
  INTERVIEW_SCHEDULED: 3,
  OFFERED: 4,
  HIRED: 5,
};

interface Step {
  state: StepState;
  detail?: string;
}

function buildSteps(
  c: CandidateDetail,
  reqId: string,
): (Step & { key: string; label: string; Icon: LucideIcon })[] {
  const status = c.applications.find((a) => a.requisition_id === reqId)?.status;
  const hasApp = status != null;
  const rank = status ? RANK[status] ?? -1 : -1;
  const isRejected = status === "REJECTED";

  const score = c.scores.find((s) => s.requisition_id === reqId);
  // Calls scoped to this role take precedence; when there are none, fall back to
  // the candidate's general screening calls (no requisition linkage — e.g. a phone
  // screen run without a role) so the score still surfaces on the Telephonic stage.
  const reqCalls = c.calls.filter((cl) => cl.requisition_id === reqId);
  const calls = reqCalls.length ? reqCalls : c.calls.filter((cl) => cl.requisition_id == null);
  const latestCall = calls.find((cl) => cl.ai_score != null) ?? calls[0];
  const callDetail =
    latestCall?.ai_score != null ? `AI ${scoreToPercent(latestCall.ai_score)}` : undefined;
  const callOngoing = calls.some((cl) =>
    ["INITIATED", "IN_PROGRESS", "CALLBACK_REQUESTED"].includes(cl.status),
  );
  const interview = (rt: string) =>
    c.interviews.find((i) => i.requisition_id === reqId && i.round_type === rt);

  // 1) Resume ATS — `passed_ats` is the authoritative pass/fail for the resume
  // stage (an application row alone is not reliable — one can exist below the
  // cutoff). Fall back to the presence of an application when the flag is absent.
  const scoreDetail = score ? `Score ${scoreToPercent(score.total_score)}` : undefined;
  const clearedAts = score?.passed_ats ?? hasApp;
  const ats: Step =
    clearedAts || hasApp
      ? { state: "passed", detail: scoreDetail }
      : score
        ? { state: "rejected", detail: scoreDetail ? `Below cutoff · ${scoreDetail}` : "Below cutoff" }
        : { state: "upcoming" };

  // 2) Telephonic screening.
  let tel: Step;
  if (rank >= RANK.SHORTLISTED) {
    tel = { state: "passed", detail: callDetail };
  } else if (callOngoing || status === "SCREENING") {
    tel = { state: "current", detail: callDetail };
  } else if (isRejected && latestCall) {
    tel = { state: "rejected", detail: callDetail };
  } else if (latestCall?.ai_score != null) {
    // A screening call finished with a score even though the application hasn't
    // formally advanced — surface the result instead of hiding it as "Upcoming".
    tel = { state: "completed", detail: callDetail };
  } else {
    tel = { state: "upcoming" };
  }

  // 3 & 4) Interview rounds.
  const round = (rt: string, nextRt?: string): Step => {
    const it = interview(rt);
    if (it) {
      const advanced = rank >= RANK.OFFERED || (nextRt ? !!interview(nextRt) : false);
      if (it.status === "COMPLETED") {
        const rating =
          it.ai_overall_rating != null ? `Rating ${scoreToPercent(it.ai_overall_rating)}` : "Completed";
        return { state: advanced ? "passed" : "completed", detail: rating };
      }
      if (["SCHEDULED", "RESCHEDULED"].includes(it.status)) {
        return { state: "current", detail: it.scheduled_at ? formatDate(it.scheduled_at) : "Scheduled" };
      }
      if (it.status === "NO_SHOW") return { state: "rejected", detail: "No show" };
      if (it.status === "CANCELLED") return { state: "rejected", detail: "Cancelled" };
      return { state: "current" };
    }
    return { state: "upcoming" };
  };

  return [
    { key: "ats", label: "Resume ATS", Icon: FileSearch, ...ats },
    { key: "tel", label: "Telephonic", Icon: Phone, ...tel },
    { key: "l1", label: "L1 Round", Icon: Users, ...round("L1", "L2") },
    { key: "l2", label: "L2 Round", Icon: Users, ...round("L2") },
  ];
}

export function RolePipeline({
  c,
  requisitionId,
}: {
  c: CandidateDetail;
  requisitionId: string;
}) {
  const steps = buildSteps(c, requisitionId);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((step, i) => {
        const meta = STATE_META[step.state];
        const Icon = step.Icon;
        return (
          <div key={step.key} className="flex items-center gap-2">
            <div className="bg-muted/30 flex min-w-[140px] flex-col gap-1.5 rounded-lg border px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <Icon className={cn("size-4", meta.iconColor)} />
                <span className="text-foreground text-xs font-semibold">{step.label}</span>
              </div>
              <Badge variant={meta.variant}>{meta.label}</Badge>
              {step.detail && (
                <span className="text-muted-foreground text-[11px]">{step.detail}</span>
              )}
            </div>
            {i < steps.length - 1 && (
              <ChevronRight className="text-muted-foreground/40 size-4 shrink-0" />
            )}
          </div>
        );
      })}
    </div>
  );
}
