"use client";

import {
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock,
  FileSearch,
  MinusCircle,
  Phone,
  Users,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { cn, formatDate, formatNumber, scoreToPercent } from "@/lib/utils";
import type { CandidateDetail } from "@/lib/types";

/**
 * Per-role hiring pipeline for one requisition: the status of each stage the
 * candidate moves through — Resume ATS → Telephonic → L1 → L2 — derived from the
 * candidate's score, application status, screening calls, and interviews for
 * that role. This complements the single "current status" badge by showing where
 * the candidate stands at every step.
 *
 * A step is only "reachable" once the previous gate has cleared; steps after a
 * failed/unfinished gate show "Not reached" rather than "Upcoming".
 */

type StepState = "passed" | "completed" | "current" | "rejected" | "upcoming" | "na";

type Tone = "green" | "blue" | "amber" | "red" | "gray";

const STATE_META: Record<StepState, { tone: Tone; label: string; Icon: LucideIcon }> = {
  passed: { tone: "green", label: "Passed", Icon: CheckCircle2 },
  completed: { tone: "blue", label: "Completed", Icon: CheckCircle2 },
  current: { tone: "amber", label: "In progress", Icon: Clock },
  rejected: { tone: "red", label: "Did not clear", Icon: XCircle },
  upcoming: { tone: "gray", label: "Upcoming", Icon: Circle },
  na: { tone: "gray", label: "Not reached", Icon: MinusCircle },
};

const ICON_COLOR: Record<StepState, string> = {
  passed: "text-emerald-600",
  completed: "text-blue-600",
  current: "text-amber-600",
  rejected: "text-red-600",
  upcoming: "text-slate-400",
  na: "text-slate-300",
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

  // 1) Resume ATS — pass/fail is the score vs. the ATS cutoff (passed_ats from the
  // backend), NOT whether an application row exists (one can exist below cutoff).
  let ats: Step;
  if (!score) {
    ats = { state: "upcoming" };
  } else if (score.passed_ats) {
    ats = { state: "passed", detail: `Score ${scoreToPercent(score.total_score)}` };
  } else {
    ats = { state: "rejected", detail: `Below cutoff · ${scoreToPercent(score.total_score)}` };
  }

  // 2) Telephonic screening — only reachable once the resume clears ATS.
  let tel: Step;
  if (rank >= RANK.SHORTLISTED) {
    tel = { state: "passed", detail: callDetail };
  } else if (callOngoing || status === "SCREENING") {
    tel = { state: "current", detail: callDetail };
  } else if (isRejected && latestCall) {
    tel = { state: "rejected", detail: callDetail };
  } else {
    tel = { state: ats.state === "passed" ? "upcoming" : "na" };
  }

  // 3 & 4) Interview rounds — use the round's own record when present, else gate
  // reachability on the previous step clearing.
  const round = (rt: string, nextRt: string | undefined, reachable: boolean): Step => {
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
    return { state: reachable ? "upcoming" : "na" };
  };

  const l1 = round("L1", "L2", tel.state === "passed");
  const l2 = round("L2", undefined, l1.state === "passed" || l1.state === "completed");

  return [
    { key: "ats", label: "Resume ATS", Icon: FileSearch, ...ats },
    { key: "tel", label: "Telephonic", Icon: Phone, ...tel },
    { key: "l1", label: "L1 Round", Icon: Users, ...l1 },
    { key: "l2", label: "L2 Round", Icon: Users, ...l2 },
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
