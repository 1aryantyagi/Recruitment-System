"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/components/ui/Toast";
import { useInterviewers, useOpenSlots } from "@/lib/meta";
import { apiPost } from "@/lib/api";
import { ROUND_TYPES, type Interview, type OpenSlot } from "@/lib/types";
import { SlotPicker } from "./SlotPicker";

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
  const { data: openSlots, loading: slotsLoading } = useOpenSlots(
    open ? requisitionId : undefined,
  );
  const [roundType, setRoundType] = useState("L1");
  const [interviewerId, setInterviewerId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [meetingLink, setMeetingLink] = useState("");
  const [selectedSlot, setSelectedSlot] = useState<OpenSlot | null>(null);
  // Pick from interviewer slots (default) vs. enter a custom time.
  const [manual, setManual] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Slot picking is the default when the requisition has interviewer slots.
  const useSlots = !!requisitionId && !manual;

  function reset() {
    setScheduledAt("");
    setMeetingLink("");
    setInterviewerId("");
    setSelectedSlot(null);
    setManual(false);
  }

  function selectSlot(slot: OpenSlot) {
    setSelectedSlot(slot);
    setInterviewerId(slot.interviewer_id);
    setScheduledAt(slot.start_utc);
  }

  async function submit() {
    const scheduledIso = useSlots
      ? selectedSlot?.start_utc
      : scheduledAt && new Date(scheduledAt).toISOString();
    if (!scheduledIso) {
      toast.error(useSlots ? "Pick a slot" : "Pick a date & time");
      return;
    }
    setSubmitting(true);
    try {
      await apiPost<Interview>("/interviews", {
        candidate_id: candidateId,
        requisition_id: requisitionId || undefined,
        interviewer_id: interviewerId || undefined,
        round_type: roundType,
        scheduled_at: scheduledIso,
        meeting_link: meetingLink || undefined,
      });
      toast.success("Interview scheduled");
      onScheduled?.();
      onClose();
      reset();
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

        {useSlots ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">
                Available slots
              </span>
              <button
                type="button"
                className="text-xs text-indigo-600 hover:underline"
                onClick={() => setManual(true)}
              >
                Enter time manually
              </button>
            </div>
            <SlotPicker
              slots={openSlots}
              loading={slotsLoading}
              selected={selectedSlot}
              onSelect={selectSlot}
            />
          </div>
        ) : (
          <>
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
            {!!requisitionId && (
              <button
                type="button"
                className="text-xs text-indigo-600 hover:underline"
                onClick={() => {
                  setManual(false);
                  setScheduledAt("");
                }}
              >
                Pick from interviewer slots
              </button>
            )}
          </>
        )}

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
