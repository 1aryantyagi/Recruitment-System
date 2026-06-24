"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { apiPost } from "@/lib/api";
import { useStatusReasons } from "@/lib/meta";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function BlacklistModal({
  open,
  onOpenChange,
  candidateId,
  candidateName,
  onDone,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  candidateId: string;
  candidateName?: string;
  onDone?: () => void;
}) {
  const { data: reasons } = useStatusReasons("BLACKLISTED");
  const [reasonId, setReasonId] = useState<string>("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await apiPost(`/candidates/${candidateId}/blacklist`, {
        reason_id: reasonId || undefined,
        note: note.trim() || undefined,
      });
      toast.success("Candidate blacklisted");
      onDone?.();
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Blacklist candidate</DialogTitle>
          <DialogDescription>
            {candidateName ? `${candidateName} ` : "This candidate "}
            will be marked ineligible and dropped from all active pipelines.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Reason</Label>
            <Select value={reasonId} onValueChange={setReasonId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a reason" />
              </SelectTrigger>
              <SelectContent>
                {(reasons ?? []).map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.reason}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Note (optional)</Label>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={submit} disabled={submitting}>
            {submitting && <Loader2 className="size-4 animate-spin" />}
            Blacklist
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
