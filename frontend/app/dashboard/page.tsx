"use client";

import Link from "next/link";
import {
  Users,
  Briefcase,
  FileText,
  PhoneCall,
  CalendarClock,
  ClipboardCheck,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AppShell, PageHeader } from "@/components/AppShell";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/Table";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/Spinner";
import { apiGet } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import { formatNumber, formatPercent, titleCase } from "@/lib/utils";
import type { DashboardAnalytics } from "@/lib/types";

const FUNNEL_COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#a855f7",
  "#ec4899",
  "#f59e0b",
  "#10b981",
  "#0ea5e9",
  "#14b8a6",
];

export default function DashboardPage() {
  return (
    <AppShell>
      <DashboardContent />
    </AppShell>
  );
}

function DashboardContent() {
  const { data, loading, error, reload } = useFetch<DashboardAnalytics>(
    () => apiGet<DashboardAnalytics>("/analytics/dashboard"),
    [],
  );

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <EmptyState title="No analytics data" />;

  const kpis = [
    { label: "Candidates", value: data.totals.candidates, icon: Users },
    {
      label: "Open Requisitions",
      value: data.totals.open_requisitions,
      icon: Briefcase,
    },
    { label: "Applications", value: data.totals.applications, icon: FileText },
    {
      label: "Screening Calls",
      value: data.totals.screening_calls,
      icon: PhoneCall,
    },
    {
      label: "Interviews",
      value: data.totals.interviews,
      icon: CalendarClock,
    },
    {
      label: "Feedback Submitted",
      value: data.totals.feedback_submitted,
      icon: ClipboardCheck,
    },
  ];

  const funnelData = (data.funnel ?? []).map((f) => ({
    stage: titleCase(f.stage),
    count: f.count,
    conversion_rate: f.conversion_rate,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Recruitment pipeline at a glance"
      />

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <Card key={kpi.label}>
              <CardBody className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-2xl font-semibold text-slate-800">
                    {formatNumber(kpi.value)}
                  </p>
                  <p className="text-xs text-slate-500">{kpi.label}</p>
                </div>
              </CardBody>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Funnel chart */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Hiring Funnel"
            description={
              data.hire_rate !== null && data.hire_rate !== undefined
                ? `Hire rate: ${formatPercent(data.hire_rate)}`
                : undefined
            }
          />
          <CardBody>
            {funnelData.length === 0 ? (
              <EmptyState title="No funnel data" />
            ) : (
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={funnelData}
                    margin={{ top: 8, right: 8, left: -16, bottom: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis
                      dataKey="stage"
                      tick={{ fontSize: 11, fill: "#64748b" }}
                      interval={0}
                      angle={-15}
                      textAnchor="end"
                      height={50}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "#64748b" }}
                      allowDecimals={false}
                    />
                    <Tooltip
                      cursor={{ fill: "#f8fafc" }}
                      contentStyle={{
                        borderRadius: 8,
                        border: "1px solid #e2e8f0",
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                      {funnelData.map((_, i) => (
                        <Cell
                          key={i}
                          fill={FUNNEL_COLORS[i % FUNNEL_COLORS.length]}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardBody>
        </Card>

        {/* Time to hire */}
        <Card>
          <CardHeader title="Time to Hire" />
          <CardBody className="space-y-4">
            <div>
              <p className="text-3xl font-semibold text-slate-800">
                {data.time_to_hire?.overall_avg_days != null
                  ? formatNumber(data.time_to_hire.overall_avg_days, 1)
                  : "—"}
              </p>
              <p className="text-xs text-slate-500">Avg days to hire</p>
            </div>
            <div>
              <p className="text-2xl font-semibold text-slate-800">
                {formatNumber(data.time_to_hire?.hired_count ?? 0)}
              </p>
              <p className="text-xs text-slate-500">Total hired</p>
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Sources table */}
        <Card>
          <CardHeader title="Source Effectiveness" />
          {(data.sources ?? []).length === 0 ? (
            <EmptyState title="No source data" />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Source</TH>
                  <TH className="text-right">Candidates</TH>
                  <TH className="text-right">Avg Match</TH>
                  <TH className="text-right">Hired</TH>
                  <TH className="text-right">Hire Rate</TH>
                </TR>
              </THead>
              <TBody>
                {data.sources.map((s) => (
                  <TR key={s.source} className="hover:bg-slate-50">
                    <TD className="font-medium text-slate-700">
                      {titleCase(s.source)}
                    </TD>
                    <TD className="text-right">{formatNumber(s.candidates)}</TD>
                    <TD className="text-right">
                      {s.avg_match_score != null
                        ? formatNumber(s.avg_match_score, 1)
                        : "—"}
                    </TD>
                    <TD className="text-right">{formatNumber(s.hired)}</TD>
                    <TD className="text-right">
                      {formatPercent(s.hire_rate)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </Card>

        {/* Open requisitions */}
        <Card>
          <CardHeader title="Open Requisitions" />
          {(data.open_requisitions ?? []).length === 0 ? (
            <EmptyState title="No open requisitions" />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Title</TH>
                  <TH className="text-right">Days Open</TH>
                  <TH className="text-right">Openings</TH>
                  <TH className="text-right">Pipeline</TH>
                </TR>
              </THead>
              <TBody>
                {data.open_requisitions.map((r) => (
                  <TR key={r.id} className="hover:bg-slate-50">
                    <TD>
                      <Link
                        href={`/jobs/${r.id}`}
                        className="font-medium text-indigo-600 hover:underline"
                      >
                        {r.title}
                      </Link>
                    </TD>
                    <TD className="text-right">{formatNumber(r.days_open)}</TD>
                    <TD className="text-right">{formatNumber(r.openings)}</TD>
                    <TD className="text-right">
                      {formatNumber(r.pipeline_count)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </Card>
      </div>
    </div>
  );
}
