"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/components/ui/Toast";
import { useInterviewers, useInterviewerSlots } from "@/lib/meta";
import { apiDelete, apiPatch, apiPost } from "@/lib/api";

// date.weekday() bit positions: Mon=0 … Sun=6.
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DEFAULT_MASK = 0b0011111; // Mon–Fri

function maskLabel(mask: number): string {
  const days = WEEKDAYS.filter((_, i) => (mask >> i) & 1);
  if (days.length === 5 && mask === DEFAULT_MASK) return "Mon–Fri";
  return days.join(", ") || "—";
}

export function InterviewerSlotsPanel() {
  const toast = useToast();
  const { data: interviewers } = useInterviewers();
  const [interviewerId, setInterviewerId] = useState("");
  const { data: slots, loading, reload } = useInterviewerSlots(interviewerId);

  const [time, setTime] = useState("16:30");
  const [mask, setMask] = useState(DEFAULT_MASK);
  const [duration, setDuration] = useState(60);
  const [busy, setBusy] = useState(false);

  function toggleDay(i: number) {
    setMask((m) => m ^ (1 << i));
  }

  async function addSlot() {
    if (!interviewerId) {
      toast.error("Select an interviewer first");
      return;
    }
    setBusy(true);
    try {
      await apiPost(`/interviewers/${interviewerId}/slots`, {
        slot_time: time,
        weekday_mask: mask,
        duration_minutes: duration,
      });
      toast.success("Slot added");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(slotId: string, isActive: boolean) {
    try {
      await apiPatch(`/interviewers/${interviewerId}/slots/${slotId}`, {
        is_active: !isActive,
      });
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function remove(slotId: string) {
    try {
      await apiDelete(`/interviewers/${interviewerId}/slots/${slotId}`);
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="max-w-sm">
        <Select
          label="Interviewer"
          options={(interviewers ?? []).map((i) => ({
            value: i.id,
            label: `${i.name} (${i.email})`,
          }))}
          value={interviewerId}
          onChange={(e) => setInterviewerId(e.target.value)}
          placeholder="Select an interviewer…"
        />
      </div>

      {interviewerId && (
        <>
          <ul className="space-y-1">
            {(slots ?? []).map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm"
              >
                <span className="text-slate-700">
                  <span className="font-medium">{s.slot_time}</span> ·{" "}
                  {maskLabel(s.weekday_mask)} · {s.duration_minutes} min
                  {!s.is_active && (
                    <span className="ml-2 text-xs text-amber-600">(inactive)</span>
                  )}
                </span>
                <span className="flex items-center gap-3">
                  <button
                    type="button"
                    className="text-xs text-indigo-600 hover:underline"
                    onClick={() => toggleActive(s.id, s.is_active)}
                  >
                    {s.is_active ? "Disable" : "Enable"}
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(s.id)}
                    className="text-slate-400 hover:text-red-600"
                    aria-label="Delete slot"
                  >
                    <Trash2 size={15} />
                  </button>
                </span>
              </li>
            ))}
            {!loading && (slots ?? []).length === 0 && (
              <li className="text-sm text-slate-500">No slots yet.</li>
            )}
          </ul>

          <div className="rounded-xl border border-slate-200 p-3">
            <p className="mb-2 text-xs font-medium text-slate-600">Add a slot</p>
            <div className="flex flex-wrap items-end gap-3">
              <Input
                label="Time (local)"
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                className="w-32"
              />
              <Input
                label="Duration (min)"
                type="number"
                value={String(duration)}
                onChange={(e) => setDuration(Number(e.target.value) || 60)}
                className="w-28"
              />
              <div>
                <span className="mb-1 block text-xs font-medium text-slate-600">
                  Days
                </span>
                <div className="flex gap-1">
                  {WEEKDAYS.map((d, i) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => toggleDay(i)}
                      className={
                        "rounded-md px-2 py-1 text-xs " +
                        ((mask >> i) & 1
                          ? "bg-indigo-600 text-white"
                          : "bg-slate-100 text-slate-600")
                      }
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
              <Button onClick={addSlot} loading={busy}>
                Add slot
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
