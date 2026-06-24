"use client";

import { useEffect, useMemo, useState } from "react";
import {
  addMonths,
  endOfMonth,
  endOfWeek,
  format,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { CalendarClock, ChevronLeft, ChevronRight, Plus } from "lucide-react";

import { apiList } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import type { InterviewListItem, ListResponse } from "@/lib/types";
import { formatPercent } from "@/lib/utils";
import { PageHeader } from "@/components/common/page-header";
import { KpiCard } from "@/components/common/kpi-card";
import { ErrorState } from "@/components/common/states";
import { MonthCalendar, AgendaList } from "@/components/interviews/calendar";
import { InterviewDetailSheet } from "@/components/interviews/interview-detail-sheet";
import { ScheduleInterviewModal } from "@/components/interviews/schedule-interview-modal";
import { FeedbackModal } from "@/components/interviews/feedback-modal";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function InterviewsPage() {
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [view, setView] = useState("month");
  const [selected, setSelected] = useState<InterviewListItem | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleCandidate, setScheduleCandidate] = useState<string | undefined>();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackIv, setFeedbackIv] = useState<InterviewListItem | null>(null);

  // Prefill schedule from ?candidate= without useSearchParams (avoids Suspense req).
  useEffect(() => {
    const c = new URLSearchParams(window.location.search).get("candidate");
    if (c) {
      setScheduleCandidate(c);
      setScheduleOpen(true);
    }
  }, []);

  const range = useMemo(() => {
    const from = startOfWeek(startOfMonth(month), { weekStartsOn: 1 });
    const to = endOfWeek(endOfMonth(month), { weekStartsOn: 1 });
    return { from: from.toISOString(), to: to.toISOString() };
  }, [month]);

  const { data, loading, error, reload } = useFetch<ListResponse<InterviewListItem>>(
    (signal) => apiList<InterviewListItem>("/interviews", { ...range, limit: 200 }, signal),
    [range.from, range.to],
  );

  const interviews = data?.data ?? [];
  const total = interviews.length;
  const completed = interviews.filter((i) => i.status === "COMPLETED").length;
  const noShow = interviews.filter((i) => i.status === "NO_SHOW").length;
  const rescheduled = interviews.filter((i) => i.status === "RESCHEDULED").length;

  const openDetail = (iv: InterviewListItem) => {
    setSelected(iv);
    setDetailOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Interviews"
        description="Schedule, track, and review interview rounds."
        action={
          <Button onClick={() => { setScheduleCandidate(undefined); setScheduleOpen(true); }}>
            <Plus className="size-4" /> Schedule
          </Button>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="This period" value={total} icon={CalendarClock} accent="primary" />
        <KpiCard label="Completed" value={completed} accent="emerald" />
        <KpiCard label="No-show rate" value={formatPercent(total ? noShow / total : 0)} accent="rose" />
        <KpiCard label="Reschedule rate" value={formatPercent(total ? rescheduled / total : 0)} accent="amber" />
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon-sm" onClick={() => setMonth((m) => subMonths(m, 1))} aria-label="Previous month">
            <ChevronLeft className="size-4" />
          </Button>
          <span className="min-w-[140px] text-center text-sm font-semibold">{format(month, "MMMM yyyy")}</span>
          <Button variant="outline" size="icon-sm" onClick={() => setMonth((m) => addMonths(m, 1))} aria-label="Next month">
            <ChevronRight className="size-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setMonth(startOfMonth(new Date()))}>Today</Button>
        </div>
        <Tabs value={view} onValueChange={setView}>
          <TabsList>
            <TabsTrigger value="month">Month</TabsTrigger>
            <TabsTrigger value="agenda">Agenda</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {loading ? (
        <Skeleton className="h-[520px] w-full rounded-xl" />
      ) : error ? (
        <ErrorState description={error} onRetry={reload} />
      ) : view === "month" ? (
        <MonthCalendar month={month} interviews={interviews} onSelect={openDetail} />
      ) : interviews.length ? (
        <AgendaList interviews={interviews} onSelect={openDetail} />
      ) : (
        <div className="text-muted-foreground rounded-xl border border-dashed py-16 text-center text-sm">
          No interviews scheduled this period.
        </div>
      )}

      <InterviewDetailSheet
        interview={selected}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onChanged={reload}
        onOpenFeedback={(iv) => {
          setDetailOpen(false);
          setFeedbackIv(iv);
          setFeedbackOpen(true);
        }}
      />
      <ScheduleInterviewModal
        open={scheduleOpen}
        onOpenChange={setScheduleOpen}
        defaultCandidateId={scheduleCandidate}
        onScheduled={reload}
      />
      <FeedbackModal
        open={feedbackOpen}
        onOpenChange={setFeedbackOpen}
        interviewId={feedbackIv?.id ?? null}
        candidateName={feedbackIv?.candidate_name ?? undefined}
        onSubmitted={reload}
      />
    </>
  );
}
