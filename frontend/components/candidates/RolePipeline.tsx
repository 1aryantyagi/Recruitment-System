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
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import { formatDate, formatNumber } from "@/lib/utils";
import type { CandidateDetail } from "@/lib/types";

/**
 * Per-role hiring pipeline for one requisition: the status of each stage the
 * candidate moves through — Resume ATS → Telephonic → L1 → L2 — derived from the
 * candidate's score, application status, screening calls, and interviews for
 * that role. This complements the single "current status" badge by showing where
 * the candidate stands at every step.
 */

type StepState = "passed" | "completed" | "current" | "rejected" | "upcoming";

type Tone = "green" | "blue" | "amber" | "red" | "gray";

const STATE_META: Record<StepState, { tone: Tone; label: string; Icon: LucideIcon }> = {
  passed: { tone: "green", label: "Passed", Icon: CheckCircle2 },
  completed: { tone: "blue", label: "Completed", Icon: CheckCircle2 },
  current: { tone: "amber", label: "In progress", Icon: Clock },
  rejected: { tone: "red", label: "Did not clear", Icon: XCircle },
  upcoming: { tone: "gray", label: "Upcoming", Icon: Circle },
};

const ICON_COLOR: Record<StepState, string> = {
  passed: "text-emerald-600",
  completed: "text-blue-600",
  current: "text-amber-600",
  rejected: "text-red-600",
  upcoming: "text-slate-300",
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

function buildSteps(c: CandidateDetail, reqId: string): (Step & { key: string; label: string; Icon: LucideIcon })[] {
  const status = c.applications.find((a) => a.requisition_id === reqId)?.status;
  const hasApp = status != null;
  const rank = status ? RANK[status] ?? -1 : -1;
  const isRejected = status === "REJECTED";

  const score = c.scores.find((s) => s.requisition_id === reqId);
  const calls = c.calls.filter((cl) => cl.requisition_id === reqId);
  const latestCall = calls.find((cl) => cl.ai_score != null) ?? calls[0];
  const callDetail =
    latestCall?.ai_score != null ? `AI score ${formatNumber(latestCall.ai_score, 1)}` : undefined;
  const callOngoing = calls.some((cl) =>
    ["INITIATED", "IN_PROGRESS", "CALLBACK_REQUESTED"].includes(cl.status),
  );
  const interview = (rt: string) =>
    c.interviews.find((i) => i.requisition_id === reqId && i.round_type === rt);

  // 1) Resume ATS — an application row exists iff the resume cleared the cutoff
  // (above-threshold candidates are auto-linked into the pipeline).
  const scoreDetail = score ? `Score ${formatNumber(score.total_score, 1)}` : undefined;
  const ats: Step = hasApp
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
          it.ai_overall_rating != null ? `Rating ${formatNumber(it.ai_overall_rating, 1)}` : "Completed";
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

export function RolePipeline({ c, requisitionId }: { c: CandidateDetail; requisitionId: string }) {
  const steps = buildSteps(c, requisitionId);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((step, i) => {
        const meta = STATE_META[step.state];
        const Icon = step.Icon;
        return (
          <div key={step.key} className="flex items-center gap-2">
            <div className="flex min-w-[150px] flex-col gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <Icon className={cn("h-4 w-4", ICON_COLOR[step.state])} />
                <span className="text-xs font-semibold text-slate-700">{step.label}</span>
              </div>
              <Badge tone={meta.tone}>{meta.label}</Badge>
              {step.detail && <span className="text-[11px] text-slate-500">{step.detail}</span>}
            </div>
            {i < steps.length - 1 && (
              <ChevronRight className="h-4 w-4 shrink-0 text-slate-300" />
            )}
          </div>
        );
      })}
    </div>
  );
}
