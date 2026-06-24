"use client";

import { useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import {
  ClipboardCheck,
  ExternalLink,
  Upload,
  Video,
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { apiPatch, apiUpload } from "@/lib/api";
import type { InterviewListItem } from "@/lib/types";
import { INTERVIEW_STATUSES } from "@/lib/types";
import { scoreToPercent, titleCase } from "@/lib/utils";
import { Stat } from "@/components/common/stat";
import { ScoreRing } from "@/components/common/score";
import { InterviewStatusBadge } from "@/components/common/badges";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function InterviewDetailSheet({
  interview,
  open,
  onOpenChange,
  onChanged,
  onOpenFeedback,
}: {
  interview: InterviewListItem | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onChanged?: () => void;
  onOpenFeedback: (iv: InterviewListItem) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  if (!interview) return null;
  const iv = interview;

  const changeStatus = async (status: string) => {
    setBusy(true);
    try {
      await apiPatch(`/interviews/${iv.id}`, { status });
      toast.success(`Marked ${titleCase(status)}`);
      onChanged?.();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const uploadRecording = async (file: File) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await apiUpload(`/interviews/${iv.id}/recording`, fd);
      toast.success("Recording uploaded — analysis is processing");
      onChanged?.();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle>{iv.candidate_name ?? "Candidate"}</SheetTitle>
          <SheetDescription>
            {iv.round_type} · {iv.requisition_title ?? "—"}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-5 p-6">
          <div className="flex items-center justify-between">
            <InterviewStatusBadge status={iv.status} />
            {iv.ai_overall_rating != null && <ScoreRing score={iv.ai_overall_rating} size={48} />}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Stat
              label="Scheduled"
              value={iv.scheduled_at ? format(parseISO(iv.scheduled_at), "MMM d, HH:mm") : "—"}
            />
            <Stat label="Interviewer" value={iv.interviewer?.name ?? "—"} />
            <Stat label="Round" value={`${iv.round_type}${iv.round_number ? ` · ${iv.round_number}` : ""}`} />
            <Stat label="AI rating" value={iv.ai_overall_rating != null ? `${scoreToPercent(iv.ai_overall_rating)}` : "—"} />
          </div>

          {iv.meeting_link && (
            <Button variant="outline" className="w-full" asChild>
              <a href={iv.meeting_link} target="_blank" rel="noreferrer">
                <Video className="size-4" /> Join meeting <ExternalLink className="size-3.5" />
              </a>
            </Button>
          )}

          <Separator />

          <div className="space-y-1.5">
            <label className="text-sm font-medium">Update status</label>
            <Select value={iv.status} onValueChange={changeStatus} disabled={busy}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {INTERVIEW_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>{titleCase(s)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" disabled={busy} onClick={() => fileInput.current?.click()}>
              <Upload className="size-4" /> Recording
            </Button>
            <input
              ref={fileInput}
              type="file"
              accept="audio/*,video/*"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && uploadRecording(e.target.files[0])}
            />
            <Button onClick={() => onOpenFeedback(iv)}>
              <ClipboardCheck className="size-4" /> Evaluate
            </Button>
          </div>

          <Link
            href={`/candidates/${iv.candidate_id}`}
            className="text-primary inline-flex items-center gap-1 text-sm hover:underline"
          >
            View candidate profile <ExternalLink className="size-3.5" />
          </Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}
