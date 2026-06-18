"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";
import { apiGet, apiPost } from "@/lib/api";
import { titleCase } from "@/lib/utils";
import {
  RECOMMENDATIONS,
  type FeedbackResponse,
  type InterviewFeedback,
} from "@/lib/types";

const RATING_FIELDS: { key: keyof InterviewFeedback; label: string }[] = [
  { key: "technical_rating", label: "Technical" },
  { key: "communication_rating", label: "Communication" },
  { key: "problem_solving_rating", label: "Problem solving" },
  { key: "culture_fit_rating", label: "Culture fit" },
  { key: "overall_rating", label: "Overall" },
];

export function FeedbackModal({
  open,
  onClose,
  interviewId,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  interviewId: string;
  onSaved?: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<InterviewFeedback>({});
  const [ai, setAi] = useState<FeedbackResponse | null>(null);
  const [loadingAi, setLoadingAi] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoadingAi(true);
    apiGet<FeedbackResponse>(`/interviews/${interviewId}/feedback`)
      .then((res) => {
        setAi(res);
        if (res.feedback) setForm(res.feedback);
      })
      .catch(() => {
        /* feedback may not exist yet */
      })
      .finally(() => setLoadingAi(false));
  }, [open, interviewId]);

  function set<K extends keyof InterviewFeedback>(
    key: K,
    value: InterviewFeedback[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save(submit: boolean) {
    setSaving(true);
    try {
      await apiPost(`/interviews/${interviewId}/feedback`, {
        ...form,
        is_submitted: submit,
      });
      toast.success(submit ? "Feedback submitted" : "Draft saved");
      onSaved?.();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const ratingOptions = [
    { value: "", label: "—" },
    ...[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) })),
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Interview feedback"
      size="lg"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="secondary" onClick={() => save(false)} loading={saving}>
            Save draft
          </Button>
          <Button onClick={() => save(true)} loading={saving}>
            Submit
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* AI analysis panel */}
        {loadingAi ? (
          <p className="text-xs text-slate-400">Loading AI analysis…</p>
        ) : ai && (ai.ai_overall_rating != null || ai.ai_analysis) ? (
          <div className="rounded-lg bg-indigo-50/60 p-3">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-indigo-500">
              AI Analysis
              {ai.ai_overall_rating != null &&
                ` · Rating ${ai.ai_overall_rating}`}
            </p>
            {ai.ai_analysis != null && (
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-slate-600">
                {typeof ai.ai_analysis === "string"
                  ? ai.ai_analysis
                  : JSON.stringify(ai.ai_analysis, null, 2)}
              </pre>
            )}
          </div>
        ) : (
          <p className="text-xs text-slate-400">
            No AI analysis yet (upload a recording to generate one).
          </p>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {RATING_FIELDS.map((f) => (
            <Select
              key={f.key}
              label={f.label}
              options={ratingOptions}
              value={
                form[f.key] != null ? String(form[f.key] as number) : ""
              }
              onChange={(e) =>
                set(
                  f.key,
                  e.target.value
                    ? (Number(e.target.value) as never)
                    : (undefined as never),
                )
              }
            />
          ))}
        </div>

        <Select
          label="Recommendation"
          options={RECOMMENDATIONS.map((r) => ({
            value: r,
            label: titleCase(r),
          }))}
          value={form.recommendation ?? ""}
          onChange={(e) =>
            set("recommendation", (e.target.value || undefined) as never)
          }
          placeholder="—"
        />

        <Textarea
          label="Summary"
          value={form.human_summary ?? ""}
          onChange={(e) => set("human_summary", e.target.value)}
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Textarea
            label="Strengths"
            value={form.human_strengths ?? ""}
            onChange={(e) => set("human_strengths", e.target.value)}
          />
          <Textarea
            label="Concerns"
            value={form.human_concerns ?? ""}
            onChange={(e) => set("human_concerns", e.target.value)}
          />
        </div>
      </div>
    </Modal>
  );
}
