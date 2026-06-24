"use client";

import { useState } from "react";
import { format, parseISO } from "date-fns";
import { ClipboardCheck, Sparkles } from "lucide-react";

import { apiList } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import type { InterviewListItem, ListResponse } from "@/lib/types";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/states";
import { ScoreRing } from "@/components/common/score";
import { RecommendationBadge } from "@/components/common/badges";
import { AvatarName } from "@/components/common/avatar-name";
import { FeedbackModal } from "@/components/interviews/feedback-modal";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function EvaluationsPage() {
  const [tab, setTab] = useState("awaiting");
  const [activeIv, setActiveIv] = useState<InterviewListItem | null>(null);
  const [open, setOpen] = useState(false);

  const awaiting = useFetch<ListResponse<InterviewListItem>>(
    (signal) => apiList<InterviewListItem>("/interviews", { needs_feedback: true, limit: 50 }, signal),
    [],
  );
  const completed = useFetch<ListResponse<InterviewListItem>>(
    (signal) => apiList<InterviewListItem>("/interviews", { analyzed: true, limit: 50 }, signal),
    [],
  );

  const reloadAll = () => {
    awaiting.reload();
    completed.reload();
  };

  const openEval = (iv: InterviewListItem) => {
    setActiveIv(iv);
    setOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Evaluations"
        description="AI-analyzed interviews and your structured scorecards."
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="awaiting">
            Awaiting feedback{awaiting.data ? ` (${awaiting.data.total})` : ""}
          </TabsTrigger>
          <TabsTrigger value="completed">Completed evaluations</TabsTrigger>
        </TabsList>

        <TabsContent value="awaiting" className="mt-4">
          <EvalList
            state={awaiting}
            onOpen={openEval}
            emptyTitle="All caught up"
            emptyDesc="No interviews are awaiting feedback right now."
          />
        </TabsContent>
        <TabsContent value="completed" className="mt-4">
          <EvalList
            state={completed}
            onOpen={openEval}
            emptyTitle="No analyzed interviews"
            emptyDesc="AI evaluations appear here after interview recordings are processed."
          />
        </TabsContent>
      </Tabs>

      <FeedbackModal
        open={open}
        onOpenChange={setOpen}
        interviewId={activeIv?.id ?? null}
        candidateName={activeIv?.candidate_name ?? undefined}
        onSubmitted={reloadAll}
      />
    </>
  );
}

function EvalList({
  state,
  onOpen,
  emptyTitle,
  emptyDesc,
}: {
  state: ReturnType<typeof useFetch<ListResponse<InterviewListItem>>>;
  onOpen: (iv: InterviewListItem) => void;
  emptyTitle: string;
  emptyDesc: string;
}) {
  const { data, loading, error, reload } = state;
  if (loading) return <Card className="p-5"><TableSkeleton rows={5} cols={3} /></Card>;
  if (error) return <ErrorState description={error} onRetry={reload} />;
  const rows = data?.data ?? [];
  if (!rows.length)
    return <EmptyState icon={<ClipboardCheck className="size-6" />} title={emptyTitle} description={emptyDesc} />;

  return (
    <div className="space-y-2">
      {rows.map((iv) => (
        <button
          key={iv.id}
          onClick={() => onOpen(iv)}
          className="bg-card hover:bg-muted/40 flex w-full items-center gap-4 rounded-xl border p-4 text-left shadow-card transition-colors"
        >
          <ScoreRing score={iv.ai_overall_rating} size={44} />
          <div className="min-w-0 flex-1">
            <AvatarName name={iv.candidate_name} subtitle={`${iv.round_type} · ${iv.requisition_title ?? "—"}`} />
          </div>
          <div className="hidden text-right sm:block">
            <p className="text-muted-foreground text-xs">
              {iv.scheduled_at ? format(parseISO(iv.scheduled_at), "MMM d, yyyy") : "—"}
            </p>
          </div>
          {iv.feedback?.is_submitted ? (
            <RecommendationBadge recommendation={iv.feedback?.recommendation} />
          ) : (
            <Badge variant="warning" className="gap-1">
              <Sparkles className="size-3" /> Needs review
            </Badge>
          )}
        </button>
      ))}
    </div>
  );
}
