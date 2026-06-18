"use client";

import { useMemo, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface MultiSelectOption {
  value: string;
  label: string;
  group?: string;
}

export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  placeholder = "Select…",
  className,
}: {
  label?: string;
  options: MultiSelectOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query]);

  const labelFor = (value: string) =>
    options.find((o) => o.value === value)?.label ?? value;

  const toggle = (value: string) => {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  };

  return (
    <div className={cn("relative w-full", className)}>
      {label && (
        <label className="mb-1 block text-xs font-medium text-slate-600">
          {label}
        </label>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 transition hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
      >
        <span className="truncate text-left text-slate-600">
          {selected.length === 0
            ? placeholder
            : `${selected.length} selected`}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
      </button>

      {selected.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {selected.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700"
            >
              {labelFor(v)}
              <button
                type="button"
                onClick={() => toggle(v)}
                className="text-indigo-400 hover:text-indigo-700"
                aria-label={`Remove ${labelFor(v)}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {open && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              className="mb-1 h-8 w-full rounded-md border border-slate-200 px-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-200"
            />
            {filtered.length === 0 && (
              <p className="px-2 py-3 text-center text-xs text-slate-400">
                No matches
              </p>
            )}
            {filtered.map((o) => {
              const isSel = selected.includes(o.value);
              return (
                <button
                  type="button"
                  key={o.value}
                  onClick={() => toggle(o.value)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition hover:bg-slate-50",
                    isSel && "bg-indigo-50",
                  )}
                >
                  <span className="truncate text-slate-700">{o.label}</span>
                  {isSel && <Check className="h-4 w-4 text-indigo-600" />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
