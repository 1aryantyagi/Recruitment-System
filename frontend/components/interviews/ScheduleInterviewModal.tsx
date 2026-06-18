"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/components/ui/Toast";
import { useInterviewers } from "@/lib/meta";
import { apiPost } from "@/lib/api";
import { ROUND_TYPES, type Interview } from "@/lib/types";

export function ScheduleInterviewModal({
  open,
  onClose,
  candidateId,
  requisitionId,
  onScheduled,
}: {
  open: boolean;
  onClose: () => void;
  candidateId: string;
  requisitionId?: string;
  onScheduled?: () => void;
}) {
  const toast = useToast();
  const { data: interviewers } = useInterviewers();
  const [roundType, setRoundType] = useState("L1");
  const [interviewerId, setInterviewerId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [meetingLink, setMeetingLink] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    if (!scheduledAt) {
      toast.error("Pick a date & time");
      return;
    }
    setSubmitting(true);
    try {
      await apiPost<Interview>("/interviews", {
        candidate_id: candidateId,
        requisition_id: requisitionId || undefined,
        interviewer_id: interviewerId || undefined,
        round_type: roundType,
        scheduled_at: new Date(scheduledAt).toISOString(),
        meeting_link: meetingLink || undefined,
      });
      toast.success("Interview scheduled");
      onScheduled?.();
      onClose();
      // reset
      setScheduledAt("");
      setMeetingLink("");
      setInterviewerId("");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Schedule interview"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={submit} loading={submitting}>
            Schedule
          </Button>
        </>
      }
    >
      <div className="space-y-3">
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
          label="Meeting link (optional)"
          placeholder="https://meet…"
          value={meetingLink}
          onChange={(e) => setMeetingLink(e.target.value)}
        />
      </div>
    </Modal>
  );
}
