"use client";

import { useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/components/ui/Toast";
import { useInterviewers, useRequisitionInterviewers } from "@/lib/meta";
import { apiDelete, apiPost } from "@/lib/api";

/**
 * Manage which interviewers conduct rounds for a requisition. The voice agent
 * and the slot picker only offer slots belonging to assigned interviewers.
 */
export function AssignInterviewersPanel({
  requisitionId,
}: {
  requisitionId: string;
}) {
  const toast = useToast();
  const { data: assigned, reload } = useRequisitionInterviewers(requisitionId);
  const { data: allInterviewers } = useInterviewers();
  const [picked, setPicked] = useState("");
  const [busy, setBusy] = useState(false);

  const unassigned = useMemo(() => {
    const taken = new Set((assigned ?? []).map((a) => a.interviewer?.id));
    return (allInterviewers ?? []).filter((i) => !taken.has(i.id));
  }, [assigned, allInterviewers]);

  async function assign() {
    if (!picked) return;
    setBusy(true);
    try {
      await apiPost(`/requisitions/${requisitionId}/interviewers`, {
        interviewer_id: picked,
      });
      toast.success("Interviewer assigned");
      setPicked("");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(interviewerId: string) {
    try {
      await apiDelete(
        `/requisitions/${requisitionId}/interviewers/${interviewerId}`,
      );
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">
        Interview panel
      </h3>

      <ul className="mb-3 space-y-1">
        {(assigned ?? []).map((a) => (
          <li
            key={a.id}
            className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm"
          >
            <span className="text-slate-700">
              {a.interviewer?.name}{" "}
              <span className="text-slate-400">({a.interviewer?.email})</span>
            </span>
            {a.interviewer && (
              <button
                type="button"
                onClick={() => remove(a.interviewer!.id)}
                className="text-slate-400 hover:text-red-600"
                aria-label="Remove interviewer"
              >
                <Trash2 size={15} />
              </button>
            )}
          </li>
        ))}
        {(assigned ?? []).length === 0 && (
          <li className="text-sm text-slate-500">No interviewers assigned yet.</li>
        )}
      </ul>

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Select
            label="Add interviewer"
            options={unassigned.map((i) => ({
              value: i.id,
              label: `${i.name} (${i.email})`,
            }))}
            value={picked}
            onChange={(e) => setPicked(e.target.value)}
            placeholder="Select…"
          />
        </div>
        <Button onClick={assign} loading={busy} disabled={!picked}>
          Assign
        </Button>
      </div>
    </div>
  );
}
