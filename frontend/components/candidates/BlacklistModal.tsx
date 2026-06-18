"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";
import { useStatusReasons } from "@/lib/meta";
import { apiPost } from "@/lib/api";

export function BlacklistModal({
  open,
  onClose,
  candidateId,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  candidateId: string;
  onDone?: () => void;
}) {
  const toast = useToast();
  const { data: reasons } = useStatusReasons("BLACKLISTED");
  const [reasonId, setReasonId] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    setSubmitting(true);
    try {
      await apiPost(`/candidates/${candidateId}/blacklist`, {
        reason_id: reasonId || undefined,
        note: note || undefined,
      });
      toast.success("Candidate blacklisted");
      onDone?.();
      onClose();
      setReasonId("");
      setNote("");
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
      title="Blacklist candidate"
      description="This will flag the candidate as blacklisted."
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="danger" onClick={submit} loading={submitting}>
            Blacklist
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Select
          label="Reason"
          options={(reasons ?? []).map((r) => ({
            value: r.id,
            label: r.reason,
          }))}
          value={reasonId}
          onChange={(e) => setReasonId(e.target.value)}
          placeholder="Select a reason (optional)"
        />
        <Textarea
          label="Note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add context…"
        />
      </div>
    </Modal>
  );
}
