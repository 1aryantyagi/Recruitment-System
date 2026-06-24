"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarClock, Loader2, Search } from "lucide-react";
import { toast } from "sonner";

import { apiList, apiPost } from "@/lib/api";
import { useDebounce, useFetch } from "@/lib/hooks";
import { useInterviewers, useOpenSlots } from "@/lib/meta";
import type { CandidateListItem, ListResponse, RequisitionListItem } from "@/lib/types";
import { ROUND_TYPES } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const NONE = "__none__";

export function ScheduleInterviewModal({
  open,
  onOpenChange,
  defaultCandidateId,
  defaultCandidateName,
  onScheduled,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaultCandidateId?: string;
  defaultCandidateName?: string;
  onScheduled?: () => void;
}) {
  const [candidateId, setCandidateId] = useState(defaultCandidateId ?? "");
  const [candidateName, setCandidateName] = useState(defaultCandidateName ?? "");
  const [search, setSearch] = useState("");
  const [requisitionId, setRequisitionId] = useState(NONE);
  const [interviewerId, setInterviewerId] = useState("");
  const [roundType, setRoundType] = useState("L1");
  const [scheduledAt, setScheduledAt] = useState("");
  const [meetingLink, setMeetingLink] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setCandidateId(defaultCandidateId ?? "");
      setCandidateName(defaultCandidateName ?? "");
    }
  }, [open, defaultCandidateId, defaultCandidateName]);

  const debSearch = useDebounce(search, 300);
  const { data: searchResults } = useFetch<ListResponse<CandidateListItem>>(
    (signal) => apiList<CandidateListItem>("/candidates", { search: debSearch, limit: 6 }, signal),
    [debSearch],
    { enabled: !candidateId && debSearch.length > 1 },
  );

  const { data: reqs } = useFetch<ListResponse<RequisitionListItem>>(
    (signal) => apiList<RequisitionListItem>("/requisitions", { status: "OPEN", limit: 100 }, signal),
    [],
    { enabled: open },
  );
  const { data: interviewers } = useInterviewers();
  const { data: slots } = useOpenSlots(requisitionId === NONE ? undefined : requisitionId);

  const canSubmit = useMemo(
    () => !!candidateId && !!roundType && !!scheduledAt,
    [candidateId, roundType, scheduledAt],
  );

  const submit = async () => {
    setBusy(true);
    try {
      await apiPost("/interviews", {
        candidate_id: candidateId,
        requisition_id: requisitionId === NONE ? undefined : requisitionId,
        interviewer_id: interviewerId || undefined,
        round_type: roundType,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : undefined,
        meeting_link: meetingLink || undefined,
      });
      toast.success("Interview scheduled");
      onScheduled?.();
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarClock className="size-5" /> Schedule interview
          </DialogTitle>
          <DialogDescription>
            Books a round and sends a calendar invite via the scheduling agent.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Candidate */}
          <div className="space-y-1.5">
            <Label>Candidate</Label>
            {candidateId ? (
              <div className="bg-muted/50 flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
                <span className="font-medium">{candidateName || candidateId}</span>
                {!defaultCandidateId && (
                  <Button variant="ghost" size="sm" onClick={() => { setCandidateId(""); setCandidateName(""); }}>
                    Change
                  </Button>
                )}
              </div>
            ) : (
              <div className="relative">
                <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search candidate by name…"
                  className="pl-8"
                />
                {searchResults && searchResults.data.length > 0 && (
                  <div className="bg-popover absolute z-10 mt-1 w-full overflow-hidden rounded-lg border shadow-card-lg">
                    {searchResults.data.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => { setCandidateId(c.id); setCandidateName(c.full_name); setSearch(""); }}
                        className="hover:bg-accent flex w-full items-center justify-between px-3 py-2 text-left text-sm"
                      >
                        <span>{c.full_name}</span>
                        <span className="text-muted-foreground text-xs">{c.current_designation ?? ""}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Requisition</Label>
              <Select value={requisitionId} onValueChange={setRequisitionId}>
                <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>None</SelectItem>
                  {(reqs?.data ?? []).map((r) => (
                    <SelectItem key={r.id} value={r.id}>{r.title}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Round</Label>
              <Select value={roundType} onValueChange={setRoundType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROUND_TYPES.map((r) => (
                    <SelectItem key={r} value={r}>{r}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Suggested slots */}
          {slots && slots.length > 0 && (
            <div className="space-y-1.5">
              <Label>Suggested slots</Label>
              <div className="flex flex-wrap gap-1.5">
                {slots.slice(0, 6).map((s, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setInterviewerId(s.interviewer_id);
                      setScheduledAt(s.start_local.slice(0, 16));
                    }}
                    className={cn(
                      "rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors",
                      scheduledAt === s.start_local.slice(0, 16)
                        ? "border-primary bg-primary/10 text-primary"
                        : "bg-muted/50 hover:bg-muted",
                    )}
                  >
                    {s.label} · {s.interviewer_name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Interviewer</Label>
              <Select value={interviewerId} onValueChange={setInterviewerId}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {(interviewers ?? []).map((i) => (
                    <SelectItem key={i.id} value={i.id}>{i.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Date & time</Label>
              <Input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Meeting link (optional)</Label>
            <Input value={meetingLink} onChange={(e) => setMeetingLink(e.target.value)} placeholder="https://teams.microsoft.com/…" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={!canSubmit || busy}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            Schedule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
