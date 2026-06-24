"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Clock, Sparkles, TrendingUp, Trophy, Users } from "lucide-react";

import { apiGet } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import type { DashboardAnalytics, FunnelStage } from "@/lib/types";
import { cn, formatNumber, formatPercent, scoreToPercent, titleCase } from "@/lib/utils";
import { stageMeta } from "@/lib/labels";
import { PageHeader } from "@/components/common/page-header";
import { KpiCard } from "@/components/common/kpi-card";
import { ChartCard, ChartTooltip } from "@/components/common/chart-card";
import { CardGridSkeleton, ErrorState } from "@/components/common/states";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function AnalyticsPage() {
  const { data, loading, error, reload } = useFetch<DashboardAnalytics>(
    (signal) => apiGet<DashboardAnalytics>("/analytics/dashboard", { summary: true }, signal),
    [],
  );

  if (error)
    return (
      <>
        <PageHeader title="Hiring Analytics" />
        <ErrorState description={error} onRetry={reload} />
      </>
    );

  const t = data?.totals;
  const automation = data
    ? Math.round(((t!.screening_calls + t!.feedback_submitted) / Math.max(1, t!.candidates)) * 100)
    : 0;

  return (
    <>
      <PageHeader title="Hiring Analytics" description="Funnel, sources, velocity, and AI performance." />

      {loading || !data ? (
        <CardGridSkeleton count={4} />
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <KpiCard label="Time to Hire" value={data.time_to_hire?.overall_avg_days != null ? `${Math.round(data.time_to_hire.overall_avg_days)}d` : "—"} icon={Clock} accent="primary" />
          <KpiCard label="Hire Rate" value={formatPercent(data.hire_rate)} icon={TrendingUp} accent="emerald" />
          <KpiCard label="Candidates" value={formatNumber(data.totals.candidates)} icon={Users} accent="violet" />
          <KpiCard label="Total Hires" value={formatNumber(data.time_to_hire?.hired_count ?? 0)} icon={Trophy} accent="amber" />
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ChartCard title="Hiring Funnel" description="Stage-over-stage conversion">
          {loading || !data ? <Skeleton className="h-64 w-full" /> : <Funnel funnel={data.funnel} />}
        </ChartCard>

        <ChartCard title="Source Effectiveness" description="Candidates sourced by channel">
          {loading || !data ? (
            <Skeleton className="h-64 w-full" />
          ) : data.sources.length === 0 ? (
            <p className="text-muted-foreground py-16 text-center text-sm">No source data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.sources.map((s) => ({ source: titleCase(s.source), candidates: s.candidates, hired: s.hired }))}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="source" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
                <RTooltip cursor={{ fill: "var(--muted)", opacity: 0.4 }} content={<ChartTooltip />} />
                <Bar dataKey="candidates" fill="var(--chart-1)" radius={[6, 6, 0, 0]} barSize={28} />
                <Bar dataKey="hired" fill="var(--chart-2)" radius={[6, 6, 0, 0]} barSize={28} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      {/* Source table */}
      <Card className="mt-6 gap-0 overflow-hidden p-0">
        <div className="border-b p-5">
          <h3 className="text-base font-semibold">Source breakdown</h3>
          <p className="text-muted-foreground text-sm">Quality and yield by channel</p>
        </div>
        {loading ? (
          <div className="p-5"><Skeleton className="h-32 w-full" /></div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Candidates</TableHead>
                <TableHead className="text-right">Avg match</TableHead>
                <TableHead className="text-right">Hired</TableHead>
                <TableHead className="text-right">Hire rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.sources ?? []).map((s) => (
                <TableRow key={s.source}>
                  <TableCell><Badge variant="muted">{titleCase(s.source)}</Badge></TableCell>
                  <TableCell className="text-right tabular-nums">{s.candidates}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.avg_match_score != null ? scoreToPercent(s.avg_match_score) : "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.hired}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatPercent(s.hire_rate)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* AI performance (derived) */}
      <Card className="mt-6 gap-4 p-5">
        <div className="flex items-center gap-2">
          <Sparkles className="text-primary size-4" />
          <h3 className="text-base font-semibold">AI Performance</h3>
          <Badge variant="muted" className="ml-2 text-[10px]">Derived from pipeline activity</Badge>
        </div>
        {loading || !t ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <DerivedStat label="Automation rate" value={`${automation}%`} hint="Tasks handled by agents" />
            <DerivedStat label="AI screenings" value={formatNumber(t.screening_calls)} hint="Telephonic screening agent" />
            <DerivedStat label="AI evaluations" value={formatNumber(t.feedback_submitted)} hint="Interview analysis agent" />
            <DerivedStat label="Applications scored" value={formatNumber(t.applications)} hint="Resume scoring agent" />
          </div>
        )}
        <p className="text-muted-foreground text-xs">
          Cost-per-hire and diversity metrics are not tracked yet — connect a source to enable them.
        </p>
      </Card>
    </>
  );
}

function DerivedStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="bg-muted/40 rounded-xl border p-4">
      <p className="text-muted-foreground text-xs font-medium">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-muted-foreground mt-0.5 text-xs">{hint}</p>
    </div>
  );
}

function Funnel({ funnel }: { funnel: FunnelStage[] }) {
  const max = Math.max(1, ...funnel.map((s) => s.count));
  return (
    <div className="space-y-3 py-2">
      {funnel.map((s) => {
        const meta = stageMeta(s.stage as never);
        return (
          <div key={s.stage} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 font-medium">
                <span className={cn("size-2 rounded-full", meta.dot)} />
                {meta.label === "—" ? titleCase(s.stage) : meta.label}
              </span>
              <span className="text-muted-foreground tabular-nums">
                {formatNumber(s.count)}
                {s.conversion_rate != null && <span className="ml-2 text-[11px]">{formatPercent(s.conversion_rate)}</span>}
              </span>
            </div>
            <div className="bg-muted h-7 overflow-hidden rounded-lg">
              <div className={cn("h-full rounded-lg transition-all duration-700", meta.dot)} style={{ width: `${Math.max(4, (s.count / max) * 100)}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
