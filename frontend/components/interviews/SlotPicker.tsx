"use client";

import { cn } from "@/lib/utils";
import type { OpenSlot } from "@/lib/types";

/**
 * Renders the open interview slots for a requisition as selectable chips.
 * The selected slot is identified by `interviewer_id + start_utc`.
 */
export function SlotPicker({
  slots,
  loading,
  selected,
  onSelect,
}: {
  slots: OpenSlot[] | null;
  loading: boolean;
  selected: OpenSlot | null;
  onSelect: (slot: OpenSlot) => void;
}) {
  if (loading) {
    return <p className="text-sm text-slate-500">Loading available slots…</p>;
  }
  if (!slots || slots.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No open slots for this role in the current window. Assign interviewers and
        slots, or enter a time manually.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      {slots.map((s) => {
        const isSel =
          selected?.interviewer_id === s.interviewer_id &&
          selected?.start_utc === s.start_utc;
        return (
          <button
            key={`${s.interviewer_id}-${s.start_utc}`}
            type="button"
            onClick={() => onSelect(s)}
            className={cn(
              "rounded-lg border px-3 py-2 text-left text-sm transition",
              isSel
                ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
            )}
          >
            <span className="block font-medium">{s.label}</span>
            <span className="block text-xs text-slate-500">
              {s.interviewer_name}
            </span>
          </button>
        );
      })}
    </div>
  );
}
