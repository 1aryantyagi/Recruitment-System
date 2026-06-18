"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
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

const COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#ec4899",
  "#f59e0b",
  "#10b981",
  "#0ea5e9",
];

export default function AnalyticsPage() {
  return (
    <AppShell>
      <AnalyticsContent />
    </AppShell>
  );
}

function AnalyticsContent() {
  const { data, loading, error, reload } = useFetch<DashboardAnalytics>(
    () => apiGet<DashboardAnalytics>("/analytics/dashboard"),
    [],
  );

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <EmptyState title="No analytics data" />;

  const funnelData = (data.funnel ?? []).map((f) => ({
    stage: titleCase(f.stage),
    count: f.count,
  }));

  const sourceData = (data.sources ?? []).map((s) => ({
    source: titleCase(s.source),
    candidates: s.candidates,
    hired: s.hired,
    avg_match_score: s.avg_match_score ?? 0,
  }));

  const reqHealth = (data.open_requisitions ?? []).map((r) => ({
    title: r.title.length > 14 ? r.title.slice(0, 14) + "…" : r.title,
    days_open: r.days_open,
    pipeline: r.pipeline_count,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Pipeline health and source effectiveness"
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Funnel */}
        <Card>
          <CardHeader
            title="Hiring Funnel"
            description={
              data.hire_rate != null
                ? `Overall hire rate: ${formatPercent(data.hire_rate)}`
                : undefined
            }
          />
          <CardBody>
            {funnelData.length === 0 ? (
              <EmptyState title="No funnel data" />
            ) : (
              <ChartBox>
                <BarChart data={funnelData}>
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
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {funnelData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ChartBox>
            )}
          </CardBody>
        </Card>

        {/* Source effectiveness */}
        <Card>
          <CardHeader title="Source Effectiveness" />
          <CardBody>
            {sourceData.length === 0 ? (
              <EmptyState title="No source data" />
            ) : (
              <ChartBox>
                <BarChart data={sourceData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis
                    dataKey="source"
                    tick={{ fontSize: 11, fill: "#64748b" }}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    allowDecimals={false}
                  />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar
                    dataKey="candidates"
                    fill="#6366f1"
                    radius={[6, 6, 0, 0]}
                  />
                  <Bar dataKey="hired" fill="#10b981" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ChartBox>
            )}
          </CardBody>
        </Card>

        {/* Open requisition health */}
        <Card>
          <CardHeader title="Open Requisition Health (days open)" />
          <CardBody>
            {reqHealth.length === 0 ? (
              <EmptyState title="No open requisitions" />
            ) : (
              <ChartBox>
                <LineChart data={reqHealth}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis
                    dataKey="title"
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                    height={50}
                  />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line
                    type="monotone"
                    dataKey="days_open"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="pipeline"
                    stroke="#6366f1"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                </LineChart>
              </ChartBox>
            )}
          </CardBody>
        </Card>

        {/* Time to hire summary */}
        <Card>
          <CardHeader title="Time to Hire" />
          <CardBody className="grid grid-cols-2 gap-4">
            <Metric
              value={
                data.time_to_hire?.overall_avg_days != null
                  ? formatNumber(data.time_to_hire.overall_avg_days, 1)
                  : "—"
              }
              label="Avg days to hire"
            />
            <Metric
              value={formatNumber(data.time_to_hire?.hired_count ?? 0)}
              label="Total hired"
            />
            <Metric
              value={formatNumber(data.totals.candidates)}
              label="Total candidates"
            />
            <Metric
              value={formatPercent(data.hire_rate)}
              label="Hire rate"
            />
          </CardBody>
        </Card>
      </div>

      {/* Source table */}
      <Card>
        <CardHeader title="Source Breakdown" />
        {(data.sources ?? []).length === 0 ? (
          <EmptyState title="No source data" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Source</TH>
                <TH className="text-right">Candidates</TH>
                <TH className="text-right">Avg Match Score</TH>
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
                  <TD className="text-right">{formatPercent(s.hire_rate)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

const tooltipStyle = {
  borderRadius: 8,
  border: "1px solid #e2e8f0",
  fontSize: 12,
};

function ChartBox({ children }: { children: React.ReactElement }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-4">
      <p className="text-2xl font-semibold text-slate-800">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}
