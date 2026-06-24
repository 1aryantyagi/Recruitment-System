"use client";

import {
  Activity,
  BarChart3,
  CalendarClock,
  ClipboardCheck,
  FileText,
  Gauge,
  PhoneCall,
  Send,
  Sparkles,
  UserSearch,
  type LucideIcon,
} from "lucide-react";
import { formatDistanceToNow, parseISO } from "date-fns";

import { apiGet, apiList } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import type {
  CandidateListItem,
  DashboardAnalytics,
  InterviewListItem,
  ListResponse,
} from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState } from "@/components/common/states";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

interface AgentDef {
  name: string;
  description: string;
  icon: LucideIcon;
  accent: string;
  count: (t: DashboardAnalytics["totals"]) => number;
  successRate: number;
}

const AGENTS: AgentDef[] = [
  { name: "Resume Intake", description: "Parses resumes, extracts skills & profile data", icon: FileText, accent: "text-violet-500 bg-violet-500/10", count: (t) => t.candidates, successRate: 98 },
  { name: "Resume Scoring", description: "Deterministic 5-dimension match scoring", icon: Gauge, accent: "text-indigo-500 bg-indigo-500/10", count: (t) => t.applications, successRate: 99 },
  { name: "Telephonic Screening", description: "Twilio call + STT + Q&A evaluation", icon: PhoneCall, accent: "text-sky-500 bg-sky-500/10", count: (t) => t.screening_calls, successRate: 92 },
  { name: "Interview Scheduling", description: "Books rounds & sends calendar invites", icon: CalendarClock, accent: "text-emerald-500 bg-emerald-500/10", count: (t) => t.interviews, successRate: 97 },
  { name: "Interview Analysis", description: "Transcribes & analyzes recordings", icon: Sparkles, accent: "text-amber-500 bg-amber-500/10", count: (t) => t.feedback_submitted, successRate: 94 },
  { name: "Feedback Collection", description: "Notifies interviewers & captures scorecards", icon: ClipboardCheck, accent: "text-rose-500 bg-rose-500/10", count: (t) => t.feedback_submitted, successRate: 96 },
  { name: "Analytics", description: "Funnel, sources & time-to-hire aggregation", icon: BarChart3, accent: "text-teal-500 bg-teal-500/10", count: () => 0, successRate: 100 },
];

const SOON = [
  { name: "Talent Sourcing", icon: UserSearch },
  { name: "Outreach", icon: Send },
  { name: "Offer Management", icon: FileText },
];

export default function AgentsPage() {
  const { data, loading, error, reload } = useFetch<DashboardAnalytics>(
    (signal) => apiGet<DashboardAnalytics>("/analytics/dashboard", undefined, signal),
    [],
  );
  const recentCands = useFetch<ListResponse<CandidateListItem>>(
    (signal) => apiList<CandidateListItem>("/candidates", { limit: 5 }, signal),
    [],
  );
  const recentIvs = useFetch<ListResponse<InterviewListItem>>(
    (signal) => apiList<InterviewListItem>("/interviews", { limit: 5 }, signal),
    [],
  );

  if (error)
    return (
      <>
        <PageHeader title="AI Agents" />
        <ErrorState description={error} onRetry={reload} />
      </>
    );

  const t = data?.totals;

  return (
    <>
      <PageHeader
        title="AI Agents"
        description="Your multi-agent recruiting workforce, working around the clock."
        action={<Badge variant="muted" className="text-[10px]">Some metrics representative — no telemetry endpoint yet</Badge>}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Agent grid */}
        <div className="lg:col-span-2">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {AGENTS.map((a) => {
              const count = t ? a.count(t) : 0;
              const active = a.name === "Analytics" || count > 0;
              return (
                <Card key={a.name} className="gap-3 p-5">
                  <div className="flex items-start justify-between">
                    <span className={cn("flex size-10 items-center justify-center rounded-xl", a.accent)}>
                      <a.icon className="size-5" />
                    </span>
                    <Badge variant={active ? "success" : "muted"} className="gap-1">
                      <span className={cn("size-1.5 rounded-full", active ? "bg-emerald-500" : "bg-slate-400")} />
                      {active ? "Active" : "Idle"}
                    </Badge>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold">{a.name}</h3>
                    <p className="text-muted-foreground text-xs">{a.description}</p>
                  </div>
                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-2xl font-semibold tabular-nums">
                        {loading ? "—" : a.name === "Analytics" ? "∞" : formatNumber(count)}
                      </p>
                      <p className="text-muted-foreground text-xs">tasks completed</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs font-medium tabular-nums">{a.successRate}%</p>
                      <p className="text-muted-foreground text-[10px]">success</p>
                    </div>
                  </div>
                  <Progress value={a.successRate} indicatorClassName="bg-emerald-500" />
                </Card>
              );
            })}
          </div>

          <div className="mt-4 grid grid-cols-3 gap-4">
            {SOON.map((s) => (
              <Card key={s.name} className="text-muted-foreground items-center gap-2 p-4 text-center opacity-70">
                <s.icon className="mx-auto size-5" />
                <p className="text-xs font-medium">{s.name}</p>
                <Badge variant="muted" className="mx-auto text-[10px]">Coming soon</Badge>
              </Card>
            ))}
          </div>
        </div>

        {/* Activity feed */}
        <Card className="h-fit gap-4 p-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Activity className="size-4" /> Live Activity
          </h3>
          {recentCands.loading || recentIvs.loading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : (
            <ActivityFeed
              candidates={recentCands.data?.data ?? []}
              interviews={recentIvs.data?.data ?? []}
            />
          )}
        </Card>
      </div>
    </>
  );
}

function ActivityFeed({
  candidates,
  interviews,
}: {
  candidates: CandidateListItem[];
  interviews: InterviewListItem[];
}) {
  const events = [
    ...candidates.map((c) => ({
      icon: FileText,
      text: `Resume processed for ${c.full_name}`,
      agent: "Resume Intake",
      date: c.created_at,
    })),
    ...interviews.map((i) => ({
      icon: CalendarClock,
      text: `${i.round_type} interview · ${i.candidate_name ?? "candidate"}`,
      agent: "Scheduling",
      date: i.scheduled_at ?? undefined,
    })),
  ]
    .filter((e) => e.date)
    .sort((a, b) => new Date(b.date!).getTime() - new Date(a.date!).getTime())
    .slice(0, 8);

  if (!events.length)
    return <p className="text-muted-foreground text-sm">No recent activity.</p>;

  return (
    <div className="space-y-3">
      {events.map((e, i) => (
        <div key={i} className="flex items-start gap-2.5">
          <span className="bg-primary/10 text-primary mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg">
            <e.icon className="size-3.5" />
          </span>
          <div className="min-w-0">
            <p className="text-sm">{e.text}</p>
            <p className="text-muted-foreground text-xs">
              {e.agent} · {e.date ? formatDistanceToNow(parseISO(e.date), { addSuffix: true }) : ""}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
