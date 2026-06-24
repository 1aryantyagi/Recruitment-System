"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import type { InterviewFeedback, Recommendation } from "@/lib/types";
import { RECOMMENDATIONS } from "@/lib/types";
import { cn } from "@/lib/utils";
import { recommendationMeta } from "@/lib/labels";
import { ScoreRing } from "@/components/common/score";
import { LoadingState } from "@/components/common/states";
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
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface FeedbackDetail {
  ai_summary?: string | null;
  ai_strengths?: string | null;
  ai_concerns?: string | null;
}
interface FeedbackResp {
  ai_overall_rating?: number | null;
  ai_analysis?: { summary?: string; strengths?: string[]; concerns?: string[] } | null;
  feedback?: (InterviewFeedback & FeedbackDetail) | null;
}

const DIMENSIONS = [
  { key: "technical_rating", label: "Technical" },
  { key: "communication_rating", label: "Communication" },
  { key: "problem_solving_rating", label: "Problem solving" },
  { key: "culture_fit_rating", label: "Culture fit" },
  { key: "overall_rating", label: "Overall" },
] as const;

export function FeedbackModal({
  open,
  onOpenChange,
  interviewId,
  candidateName,
  onSubmitted,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  interviewId: string | null;
  candidateName?: string;
  onSubmitted?: () => void;
}) {
  const { data, loading } = useFetch<FeedbackResp>(
    (signal) => apiGet<FeedbackResp>(`/interviews/${interviewId}/feedback`, undefined, signal),
    [interviewId, open],
    { enabled: open && !!interviewId },
  );

  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [recommendation, setRecommendation] = useState<string>("");
  const [summary, setSummary] = useState("");
  const [strengths, setStrengths] = useState("");
  const [concerns, setConcerns] = useState("");
  const [busy, setBusy] = useState(false);

  const fb = data?.feedback;

  const submit = async () => {
    if (!interviewId) return;
    setBusy(true);
    try {
      await apiPost(`/interviews/${interviewId}/feedback`, {
        ...ratings,
        recommendation: recommendation || undefined,
        human_summary: summary || undefined,
        human_strengths: strengths || undefined,
        human_concerns: concerns || undefined,
        is_submitted: true,
      });
      toast.success("Evaluation submitted");
      onSubmitted?.();
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Evaluation</DialogTitle>
          <DialogDescription>
            {candidateName ? `${candidateName} · ` : ""}AI analysis and your structured scorecard.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <LoadingState label="Loading analysis…" />
        ) : (
          <div className="space-y-5">
            {/* AI analysis */}
            <div className="bg-muted/40 rounded-xl border p-4">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <Sparkles className="text-primary size-4" /> AI Analysis
                </h3>
                {data?.ai_overall_rating != null && <ScoreRing score={data.ai_overall_rating} size={44} />}
              </div>
              {fb?.ai_summary || data?.ai_analysis?.summary ? (
                <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
                  {fb?.ai_summary ?? data?.ai_analysis?.summary}
                </p>
              ) : (
                <p className="text-muted-foreground mt-2 text-sm italic">No AI analysis available yet.</p>
              )}
              {fb?.ai_strengths && (
                <p className="mt-2 text-xs"><span className="font-medium text-emerald-600 dark:text-emerald-400">Strengths: </span>{fb.ai_strengths}</p>
              )}
              {fb?.ai_concerns && (
                <p className="mt-1 text-xs"><span className="font-medium text-amber-600 dark:text-amber-400">Concerns: </span>{fb.ai_concerns}</p>
              )}
            </div>

            <Separator />

            {/* Human scorecard */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold">Your scorecard</h3>
              {DIMENSIONS.map((d) => (
                <div key={d.key} className="flex items-center justify-between gap-4">
                  <Label className="text-sm font-normal">{d.label}</Label>
                  <RatingInput
                    value={ratings[d.key] ?? (fb?.[d.key as keyof InterviewFeedback] as number) ?? 0}
                    onChange={(v) => setRatings((r) => ({ ...r, [d.key]: v }))}
                  />
                </div>
              ))}
              <div className="space-y-1.5">
                <Label>Recommendation</Label>
                <Select value={recommendation || (fb?.recommendation ?? "")} onValueChange={setRecommendation}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    {RECOMMENDATIONS.map((r) => (
                      <SelectItem key={r} value={r}>{recommendationMeta(r as Recommendation).label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Summary</Label>
                <Textarea rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} defaultValue={fb?.human_summary ?? undefined} placeholder="Overall assessment…" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Strengths</Label>
                  <Textarea rows={2} value={strengths} onChange={(e) => setStrengths(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>Concerns</Label>
                  <Textarea rows={2} value={concerns} onChange={(e) => setConcerns(e.target.value)} />
                </div>
              </div>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy || loading}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            Submit evaluation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RatingInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className={cn(
            "size-7 rounded-md border text-xs font-medium tabular-nums transition-colors",
            value >= n
              ? "border-primary bg-primary text-primary-foreground"
              : "bg-muted/40 text-muted-foreground hover:bg-muted",
          )}
        >
          {n}
        </button>
      ))}
    </div>
  );
}
