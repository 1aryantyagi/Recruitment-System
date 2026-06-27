"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, PhoneCall } from "lucide-react";
import { toast } from "sonner";

import { apiList, apiPost } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import type {
  CandidateApplication,
  CandidateScore,
  ListResponse,
  RequisitionListItem,
} from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * Role picker shown when starting a telephonic screening call. Lets the recruiter
 * choose which requisition the candidate is being judged against; the chosen
 * requisition_id is passed to POST /screening/start-call (the backend then tailors
 * the screening questions to that role). The candidate's applied roles are listed
 * first (best match pre-selected), followed by every other open requisition.
 */
export function VoiceScreeningModal({
  open,
  onOpenChange,
  candidateId,
  applications,
  scores,
  onStarted,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  candidateId: string;
  applications: CandidateApplication[];
  scores: CandidateScore[];
  onStarted?: () => void;
}) {
  // Open requisitions — fetched only while the dialog is open (mirrors the
  // schedule-interview-modal pattern). Provides titles for the "other open" group
  // and a fallback title source for applied roles without a score row.
  const { data: reqs } = useFetch<ListResponse<RequisitionListItem>>(
    (signal) => apiList<RequisitionListItem>("/requisitions", { status: "OPEN", limit: 100 }, signal),
    [],
    { enabled: open },
  );

  const [roleId, setRoleId] = useState("");
  const [busy, setBusy] = useState(false);

  // Applied requisitions, de-duped and ranked by match strength (application
  // match_score, falling back to the candidate score's total_score).
  const appliedRoleIds = useMemo(() => {
    const scoreOf = (id: string) =>
      applications.find((a) => a.requisition_id === id)?.match_score ??
      scores.find((s) => s.requisition_id === id)?.total_score ??
      0;
    const seen = new Set<string>();
    const ids: string[] = [];
    for (const a of applications) {
      if (seen.has(a.requisition_id)) continue;
      seen.add(a.requisition_id);
      ids.push(a.requisition_id);
    }
    return ids.sort((x, y) => scoreOf(y) - scoreOf(x));
  }, [applications, scores]);

  const appliedSet = useMemo(() => new Set(appliedRoleIds), [appliedRoleIds]);
  const otherOpen = (reqs?.data ?? []).filter((r) => !appliedSet.has(r.id));

  // Resolve a display title for an applied requisition: prefer the scored title,
  // then the open-requisitions list, then a truncated id (same fallback used in
  // the candidate Applications tab).
  const titleFor = (id: string) =>
    scores.find((s) => s.requisition_id === id)?.requisition_title ||
    reqs?.data.find((r) => r.id === id)?.title ||
    `${id.slice(0, 8)}…`;

  // Pre-select the best-match applied role each time the dialog opens.
  useEffect(() => {
    if (open) setRoleId(appliedRoleIds[0] ?? "");
  }, [open, appliedRoleIds]);

  const hasRoles = appliedRoleIds.length > 0 || otherOpen.length > 0;

  const start = async () => {
    if (!roleId) return;
    setBusy(true);
    try {
      await apiPost("/screening/start-call", {
        candidate_id: candidateId,
        requisition_id: roleId,
      });
      toast.success("Screening call initiated");
      onStarted?.();
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PhoneCall className="size-5" /> Start screening call
          </DialogTitle>
          <DialogDescription>
            Choose the role to screen this candidate for. The agent tailors its
            questions to the selected role.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label>Role</Label>
          <Select value={roleId} onValueChange={setRoleId}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder={hasRoles ? "Select a role" : "No roles available"} />
            </SelectTrigger>
            <SelectContent>
              {appliedRoleIds.length > 0 && (
                <SelectGroup>
                  <SelectLabel>Applied roles</SelectLabel>
                  {appliedRoleIds.map((id) => (
                    <SelectItem key={id} value={id}>
                      {titleFor(id)}
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}
              {appliedRoleIds.length > 0 && otherOpen.length > 0 && <SelectSeparator />}
              {otherOpen.length > 0 && (
                <SelectGroup>
                  <SelectLabel>Other open roles</SelectLabel>
                  {otherOpen.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.title}
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}
            </SelectContent>
          </Select>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={start} disabled={busy || !roleId}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            <PhoneCall className="size-4" /> Start call
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
