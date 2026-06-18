"use client";

import { useState } from "react";
import {
  CalendarPlus,
  Search,
  Upload,
  ClipboardCheck,
  Video,
} from "lucide-react";
import { AppShell, PageHeader } from "@/components/AppShell";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { FeedbackModal } from "@/components/interviews/FeedbackModal";
import { useAuth } from "@/lib/auth";
import { apiGet, apiPatch, apiPost, apiUpload, apiList } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import { useInterviewers } from "@/lib/meta";
import { formatDateTime, formatNumber, titleCase } from "@/lib/utils";
import {
  INTERVIEW_STATUSES,
  ROUND_TYPES,
  type CandidateListItem,
  type Interview,
} from "@/lib/types";

export default function InterviewsPage() {
  return (
    <AppShell>
      <InterviewsContent />
    </AppShell>
  );
}

function InterviewsContent() {
  const { canManageCandidates } = useAuth();
  const toast = useToast();
  const { data: interviewers } = useInterviewers();

  // candidate lookup
  const [emailQuery, setEmailQuery] = useState("");
  const [activeCandidate, setActiveCandidate] =
    useState<CandidateListItem | null>(null);
  const [lookupLoading, setLookupLoading] = useState(false);

  // schedule form
  const [roundType, setRoundType] = useState("L1");
  const [interviewerId, setInterviewerId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [meetingLink, setMeetingLink] = useState("");
  const [scheduling, setScheduling] = useState(false);

  // feedback modal
  const [feedbackFor, setFeedbackFor] = useState<string | null>(null);

  const {
    data: interviews,
    loading: ivLoading,
    error: ivError,
    reload: reloadInterviews,
  } = useFetch<Interview[]>(
    () =>
      activeCandidate
        ? apiGet<Interview[]>(`/interviews/${activeCandidate.id}`)
        : Promise.resolve([]),
    [activeCandidate?.id],
    { enabled: !!activeCandidate },
  );

  async function lookupCandidate() {
    const q = emailQuery.trim();
    if (!q) return;
    setLookupLoading(true);
    try {
      // Try direct id fetch first, fall back to email search.
      let found: CandidateListItem | null = null;
      try {
        found = await apiGet<CandidateListItem>(`/candidates/${q}`);
      } catch {
        const res = await apiList<CandidateListItem>("/candidates", {
          search: q,
          limit: 1,
        });
        found = res.data[0] ?? null;
      }
      if (found) {
        setActiveCandidate(found);
        toast.success(`Loaded ${found.full_name}`);
      } else {
        toast.error("No candidate found");
        setActiveCandidate(null);
      }
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLookupLoading(false);
    }
  }

  async function schedule() {
    if (!activeCandidate) {
      toast.error("Look up a candidate first");
      return;
    }
    if (!scheduledAt) {
      toast.error("Pick a date & time");
      return;
    }
    setScheduling(true);
    try {
      await apiPost("/interviews", {
        candidate_id: activeCandidate.id,
        interviewer_id: interviewerId || undefined,
        round_type: roundType,
        scheduled_at: new Date(scheduledAt).toISOString(),
        meeting_link: meetingLink || undefined,
      });
      toast.success("Interview scheduled");
      setScheduledAt("");
      setMeetingLink("");
      reloadInterviews();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setScheduling(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Interviews"
        description="Schedule rounds, upload recordings and capture feedback"
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Schedule panel */}
        <Card className="lg:col-span-1">
          <CardHeader title="Schedule a round" />
          <CardBody className="space-y-3">
            <div className="flex items-end gap-2">
              <Input
                label="Candidate (id or email)"
                leftIcon={<Search className="h-4 w-4" />}
                value={emailQuery}
                onChange={(e) => setEmailQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && lookupCandidate()}
              />
              <Button
                variant="outline"
                onClick={lookupCandidate}
                loading={lookupLoading}
              >
                Find
              </Button>
            </div>
            {activeCandidate && (
              <div className="rounded-lg bg-indigo-50/60 p-3 text-sm">
                <p className="font-medium text-slate-700">
                  {activeCandidate.full_name}
                </p>
                <p className="text-xs text-slate-500">
                  {activeCandidate.email}
                </p>
              </div>
            )}

            <Select
              label="Round type"
              options={ROUND_TYPES.map((r) => ({ value: r, label: r }))}
              value={roundType}
              onChange={(e) => setRoundType(e.target.value)}
            />
            <Select
              label="Interviewer"
              options={(interviewers ?? []).map((i) => ({
                value: i.id,
                label: `${i.name} (${i.email})`,
              }))}
              value={interviewerId}
              onChange={(e) => setInterviewerId(e.target.value)}
              placeholder="Unassigned"
            />
            <Input
              label="Date & time"
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
            <Input
              label="Meeting link"
              placeholder="https://meet…"
              value={meetingLink}
              onChange={(e) => setMeetingLink(e.target.value)}
            />
            <Button
              className="w-full"
              onClick={schedule}
              loading={scheduling}
              disabled={!activeCandidate || !canManageCandidates}
            >
              <CalendarPlus className="h-4 w-4" /> Schedule interview
            </Button>
          </CardBody>
        </Card>

        {/* Interviews list */}
        <Card className="lg:col-span-2">
          <CardHeader
            title={
              activeCandidate
                ? `Interviews — ${activeCandidate.full_name}`
                : "Interviews"
            }
            description={
              activeCandidate
                ? undefined
                : "Look up a candidate to view their rounds"
            }
          />
          <CardBody>
            {!activeCandidate ? (
              <EmptyState
                title="No candidate selected"
                description="Search by candidate id or email to see scheduled rounds."
              />
            ) : ivLoading ? (
              <LoadingState />
            ) : ivError ? (
              <ErrorState message={ivError} onRetry={reloadInterviews} />
            ) : !interviews || interviews.length === 0 ? (
              <EmptyState title="No interviews for this candidate" />
            ) : (
              <div className="space-y-3">
                {interviews.map((iv) => (
                  <InterviewRow
                    key={iv.id}
                    interview={iv}
                    canEdit={canManageCandidates}
                    onChanged={reloadInterviews}
                    onFeedback={() => setFeedbackFor(iv.id)}
                  />
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {feedbackFor && (
        <FeedbackModal
          open={!!feedbackFor}
          onClose={() => setFeedbackFor(null)}
          interviewId={feedbackFor}
          onSaved={reloadInterviews}
        />
      )}
    </div>
  );
}

function InterviewRow({
  interview,
  canEdit,
  onChanged,
  onFeedback,
}: {
  interview: Interview;
  canEdit: boolean;
  onChanged: () => void;
  onFeedback: () => void;
}) {
  const toast = useToast();
  const [uploading, setUploading] = useState(false);
  const [statusSaving, setStatusSaving] = useState(false);

  async function updateStatus(status: string) {
    setStatusSaving(true);
    try {
      await apiPatch(`/interviews/${interview.id}`, { status });
      toast.success("Status updated");
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setStatusSaving(false);
    }
  }

  async function uploadRecording(file: File) {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await apiUpload(`/interviews/${interview.id}/recording`, fd);
      toast.success("Recording uploaded — AI analysis running");
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Badge tone="indigo">{interview.round_type}</Badge>
            {interview.round_number != null && (
              <span className="text-xs text-slate-400">
                Round {interview.round_number}
              </span>
            )}
            <StatusBadge status={interview.status} />
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {formatDateTime(interview.scheduled_at)}
          </p>
          {interview.ai_overall_rating != null && (
            <p className="mt-1 text-xs text-slate-600">
              AI rating: {formatNumber(interview.ai_overall_rating, 1)}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {interview.meeting_link && (
            <a
              href={interview.meeting_link}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline"
            >
              <Video className="h-3.5 w-3.5" /> Join
            </a>
          )}
          {canEdit && (
            <>
              <Select
                options={INTERVIEW_STATUSES.map((s) => ({
                  value: s,
                  label: titleCase(s),
                }))}
                value={interview.status}
                onChange={(e) => updateStatus(e.target.value)}
                disabled={statusSaving}
                className="h-8 w-40 text-xs"
              />
              <label className="inline-flex h-8 cursor-pointer items-center gap-1 rounded-md border border-slate-300 px-2 text-xs text-slate-600 hover:bg-slate-50">
                <Upload className="h-3.5 w-3.5" />
                {uploading ? "…" : "Recording"}
                <input
                  type="file"
                  accept="audio/*,video/*"
                  className="hidden"
                  disabled={uploading}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadRecording(f);
                  }}
                />
              </label>
              <Button variant="outline" size="sm" onClick={onFeedback}>
                <ClipboardCheck className="h-4 w-4" /> Feedback
              </Button>
            </>
          )}
        </div>
      </div>

      {interview.ai_analysis != null && (
        <pre className="mt-3 max-h-32 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-2 text-xs text-slate-600">
          {typeof interview.ai_analysis === "string"
            ? interview.ai_analysis
            : JSON.stringify(interview.ai_analysis, null, 2)}
        </pre>
      )}
    </div>
  );
}
