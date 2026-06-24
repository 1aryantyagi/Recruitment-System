"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Briefcase,
  CalendarClock,
  Clock,
  FileText,
  Gauge,
  PhoneCall,
  Sparkles,
  TrendingUp,
  Trophy,
  Users,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { apiGet } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useFetch } from "@/lib/hooks";
import type { DashboardAnalytics, FunnelStage } from "@/lib/types";
import { cn, formatNumber, formatPercent, scoreToPercent, titleCase } from "@/lib/utils";
import { stageMeta } from "@/lib/labels";
import { PageHeader } from "@/components/common/page-header";
import { KpiCard } from "@/components/common/kpi-card";
import { ChartCard, ChartTooltip } from "@/components/common/chart-card";
import { CardGridSkeleton, ErrorState } from "@/components/common/states";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function stageCount(funnel: FunnelStage[], stage: string): number {
  return funnel.find((f) => f.stage?.toUpperCase() === stage)?.count ?? 0;
}

interface Insight {
  icon: typeof Sparkles;
  tone: "primary" | "emerald" | "amber" | "rose";
  title: string;
  detail: string;
  href: string;
}

function deriveInsights(d: DashboardAnalytics): Insight[] {
  const f = d.funnel ?? [];
  const out: Insight[] = [];
  const newCount = stageCount(f, "NEW");
  const screening = stageCount(f, "SCREENING");
  const offered = stageCount(f, "OFFERED");
  const scheduled = stageCount(f, "INTERVIEW_SCHEDULED");

  out.push({
    icon: Sparkles,
    tone: "primary",
    title: `AI matched ${formatNumber(d.totals.candidates)} candidates`,
    detail: `Ranked across ${d.totals.open_requisitions} open ${d.totals.open_requisitions === 1 ? "role" : "roles"}.`,
    href: "/candidates",
  });
  if (newCount > 0)
    out.push({
      icon: FileText,
      tone: "amber",
      title: `${formatNumber(newCount)} resumes awaiting screening`,
      detail: "New applications are queued for the screening agent.",
      href: "/pipeline",
    });
  if (offered > 0)
    out.push({
      icon: Trophy,
      tone: "emerald",
      title: `${formatNumber(offered)} offers in flight`,
      detail: "Candidates are deciding — follow up to protect acceptance.",
      href: "/pipeline",
    });
  if (scheduled > Math.max(1, d.totals.feedback_submitted))
    out.push({
      icon: AlertTriangle,
      tone: "rose",
      title: "Interview feedback gap detected",
      detail: `${scheduled} interviews vs ${d.totals.feedback_submitted} evaluations submitted.`,
      href: "/evaluations",
    });
  if (out.length < 4 && screening > 0)
    out.push({
      icon: PhoneCall,
      tone: "primary",
      title: `${formatNumber(screening)} in screening`,
      detail: "Telephonic screening agent is working through the queue.",
      href: "/pipeline",
    });
  return out.slice(0, 4);
}

const INSIGHT_TONES = {
  primary: "bg-primary/10 text-primary",
  emerald: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  amber: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  rose: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
};

export default function DashboardPage() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useFetch<DashboardAnalytics>(
    (signal) =>
      apiGet<DashboardAnalytics>("/analytics/dashboard", { summary: true }, signal),
    [],
  );

  const firstName = user?.name?.split(" ")[0] ?? "there";

  const insights = useMemo(() => (data ? deriveInsights(data) : []), [data]);

  if (error) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <ErrorState description={error} onRetry={reload} />
      </>
    );
  }

  const t = data?.totals;
  const offered = data ? stageCount(data.funnel, "OFFERED") : 0;
  const hired = data?.time_to_hire?.hired_count ?? (data ? stageCount(data.funnel, "HIRED") : 0);
  const pipelineHealth = data
    ? Math.round(
        Math.min(
          100,
          40 +
            scoreToPercent(data.hire_rate) * 0.4 +
            (data.totals.interviews > 0 ? 20 : 0),
        ),
      )
    : 0;
  const automationScore = data
    ? Math.min(
        99,
        Math.round(
          ((data.totals.screening_calls + data.totals.feedback_submitted) /
            Math.max(1, data.totals.candidates)) *
            100,
        ),
      )
    : 0;

  return (
    <>
      <PageHeader
        eyebrow={new Date().toLocaleDateString(undefined, {
          weekday: "long",
          month: "long",
          day: "numeric",
        })}
        title={`${greeting()}, ${firstName}`}
        description="Here's what's happening across your hiring pipeline today."
        action={
          <Button asChild>
            <Link href="/pipeline">
              View pipeline <ArrowRight className="size-4" />
            </Link>
          </Button>
        }
      />

      {/* KPIs */}
      {loading || !t ? (
        <CardGridSkeleton count={8} />
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <KpiCard label="Open Positions" value={formatNumber(t.open_requisitions)} icon={Briefcase} accent="primary" hint="Actively hiring" />
          <KpiCard label="Active Candidates" value={formatNumber(t.candidates)} icon={Users} accent="violet" hint="In the talent pool" />
          <KpiCard label="Interviews" value={formatNumber(t.interviews)} icon={CalendarClock} accent="primary" hint="Scheduled & completed" />
          <KpiCard label="Offers Sent" value={formatNumber(offered)} icon={FileText} accent="amber" hint="Awaiting decision" />
          <KpiCard label="Hires" value={formatNumber(hired)} icon={Trophy} accent="emerald" hint="Closed successfully" />
          <KpiCard
            label="Time to Hire"
            value={
              data?.time_to_hire?.overall_avg_days != null
                ? `${Math.round(data.time_to_hire.overall_avg_days)}d`
                : "—"
            }
            icon={Clock}
            accent="primary"
            hint="Avg. days to close"
          />
          <KpiCard label="Pipeline Health" value={`${pipelineHealth}`} icon={Gauge} accent="emerald" hint="Composite score" />
          <KpiCard label="AI Automation" value={`${automationScore}%`} icon={Bot} accent="violet" hint="Tasks handled by agents" />
        </div>
      )}

      {/* Funnel + sources */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-5">
        <ChartCard
          title="Hiring Funnel"
          description="Candidate flow & stage-over-stage conversion"
          className="lg:col-span-3"
        >
          {loading || !data ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <HiringFunnel funnel={data.funnel} />
          )}
        </ChartCard>

        <ChartCard
          title="Source Performance"
          description="Candidates by source"
          className="lg:col-span-2"
        >
          {loading || !data ? (
            <Skeleton className="h-64 w-full" />
          ) : data.sources.length === 0 ? (
            <p className="text-muted-foreground py-16 text-center text-sm">
              No source data yet.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart
                data={data.sources.map((s) => ({
                  source: titleCase(s.source),
                  candidates: s.candidates,
                  hired: s.hired,
                }))}
                layout="vertical"
                margin={{ left: 8, right: 16, top: 8, bottom: 8 }}
              >
                <CartesianGrid horizontal={false} stroke="var(--border)" />
                <XAxis type="number" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
                <YAxis
                  type="category"
                  dataKey="source"
                  width={70}
                  tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                />
                <RTooltip cursor={{ fill: "var(--muted)", opacity: 0.4 }} content={<ChartTooltip />} />
                <Bar dataKey="candidates" fill="var(--chart-1)" radius={[0, 6, 6, 0]} barSize={16} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      {/* Insights + open reqs */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <Card className="h-full gap-4">
            <CardHeader className="border-b pb-4">
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="text-primary size-4" /> AI Insights
              </CardTitle>
              <CardDescription>Signals derived from your live pipeline</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2.5 pt-0">
              {loading ? (
                <>
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                </>
              ) : (
                insights.map((ins, i) => (
                  <Link
                    key={i}
                    href={ins.href}
                    className="group hover:bg-muted/50 flex items-start gap-3 rounded-xl border p-3 transition-colors"
                  >
                    <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", INSIGHT_TONES[ins.tone])}>
                      <ins.icon className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{ins.title}</p>
                      <p className="text-muted-foreground text-xs">{ins.detail}</p>
                    </div>
                    <ArrowRight className="text-muted-foreground size-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
                  </Link>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-3">
          <Card className="h-full gap-4">
            <CardHeader className="border-b pb-4">
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingUp className="size-4" /> Open Requisitions
              </CardTitle>
              <CardDescription>Roles currently hiring, by pipeline depth</CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              {loading ? (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : data && data.open_requisitions.length > 0 ? (
                <div className="divide-y">
                  {data.open_requisitions.slice(0, 6).map((r) => (
                    <Link
                      key={r.id}
                      href={`/jobs/${r.id}`}
                      className="hover:bg-muted/40 -mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{r.title}</p>
                        <p className="text-muted-foreground text-xs">
                          {r.openings} {r.openings === 1 ? "opening" : "openings"} ·{" "}
                          {r.days_open}d open
                        </p>
                      </div>
                      <Badge variant="info">{r.pipeline_count} in pipeline</Badge>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground py-10 text-center text-sm">
                  No open requisitions.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {data?.summary && (
        <Card className="mt-6 gap-0 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Bot className="text-primary size-4" /> Analytics Agent summary
          </div>
          <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
            {data.summary}
          </p>
        </Card>
      )}
    </>
  );
}

function HiringFunnel({ funnel }: { funnel: FunnelStage[] }) {
  const stages = funnel.filter((f) => f.count >= 0);
  const max = Math.max(1, ...stages.map((s) => s.count));
  return (
    <div className="space-y-3 py-2">
      {stages.map((s) => {
        const meta = stageMeta(s.stage as never);
        const pct = (s.count / max) * 100;
        return (
          <div key={s.stage} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 font-medium">
                <span className={cn("size-2 rounded-full", meta.dot)} />
                {meta.label === "—" ? titleCase(s.stage) : meta.label}
              </span>
              <span className="text-muted-foreground tabular-nums">
                {formatNumber(s.count)}
                {s.conversion_rate != null && (
                  <span className="ml-2 text-[11px]">
                    {formatPercent(s.conversion_rate)}
                  </span>
                )}
              </span>
            </div>
            <div className="bg-muted h-7 w-full overflow-hidden rounded-lg">
              <div
                className={cn("flex h-full items-center rounded-lg transition-all duration-700", meta.dot)}
                style={{ width: `${Math.max(4, pct)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
