"use client";

import {
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  isToday,
  parseISO,
  startOfMonth,
  startOfWeek,
} from "date-fns";

import type { InterviewListItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { interviewStatusVariant } from "@/lib/labels";

const DOT: Record<string, string> = {
  info: "bg-sky-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  destructive: "bg-rose-500",
  muted: "bg-slate-400",
};

export function MonthCalendar({
  month,
  interviews,
  onSelect,
}: {
  month: Date;
  interviews: InterviewListItem[];
  onSelect: (iv: InterviewListItem) => void;
}) {
  const days = eachDayOfInterval({
    start: startOfWeek(startOfMonth(month), { weekStartsOn: 1 }),
    end: endOfWeek(endOfMonth(month), { weekStartsOn: 1 }),
  });

  const eventsForDay = (day: Date) =>
    interviews.filter((iv) => iv.scheduled_at && isSameDay(parseISO(iv.scheduled_at), day));

  return (
    <div className="bg-card overflow-hidden rounded-xl border shadow-card">
      <div className="grid grid-cols-7 border-b">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div key={d} className="text-muted-foreground p-2 text-center text-xs font-medium">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {days.map((day) => {
          const events = eventsForDay(day);
          const outside = !isSameMonth(day, month);
          return (
            <div
              key={day.toISOString()}
              className={cn(
                "min-h-[104px] border-r border-b p-1.5 [&:nth-child(7n)]:border-r-0",
                outside && "bg-muted/30",
              )}
            >
              <div
                className={cn(
                  "mb-1 flex size-6 items-center justify-center rounded-full text-xs tabular-nums",
                  isToday(day) ? "bg-primary text-primary-foreground font-semibold" : "text-muted-foreground",
                  outside && "opacity-50",
                )}
              >
                {format(day, "d")}
              </div>
              <div className="space-y-1">
                {events.slice(0, 3).map((iv) => (
                  <button
                    key={iv.id}
                    onClick={() => onSelect(iv)}
                    className="hover:bg-accent flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-[11px] transition-colors"
                  >
                    <span className={cn("size-1.5 shrink-0 rounded-full", DOT[interviewStatusVariant(iv.status)])} />
                    <span className="truncate font-medium">{iv.candidate_name ?? "Candidate"}</span>
                    <span className="text-muted-foreground ml-auto shrink-0">{iv.round_type}</span>
                  </button>
                ))}
                {events.length > 3 && (
                  <p className="text-muted-foreground px-1.5 text-[10px]">+{events.length - 3} more</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function AgendaList({
  interviews,
  onSelect,
}: {
  interviews: InterviewListItem[];
  onSelect: (iv: InterviewListItem) => void;
}) {
  const sorted = [...interviews].sort(
    (a, b) => new Date(a.scheduled_at ?? 0).getTime() - new Date(b.scheduled_at ?? 0).getTime(),
  );
  return (
    <div className="bg-card divide-y rounded-xl border shadow-card">
      {sorted.map((iv) => (
        <button
          key={iv.id}
          onClick={() => onSelect(iv)}
          className="hover:bg-muted/40 flex w-full items-center gap-3 px-4 py-3 text-left transition-colors"
        >
          <div className="text-center">
            <p className="text-xs font-medium tabular-nums">
              {iv.scheduled_at ? format(parseISO(iv.scheduled_at), "MMM d") : "—"}
            </p>
            <p className="text-muted-foreground text-xs tabular-nums">
              {iv.scheduled_at ? format(parseISO(iv.scheduled_at), "HH:mm") : ""}
            </p>
          </div>
          <span className={cn("h-8 w-0.5 rounded-full", DOT[interviewStatusVariant(iv.status)])} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{iv.candidate_name ?? "Candidate"}</p>
            <p className="text-muted-foreground truncate text-xs">
              {iv.round_type} · {iv.requisition_title ?? "—"}
            </p>
          </div>
        </button>
      ))}
    </div>
  );
}
