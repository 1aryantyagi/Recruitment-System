import { cn } from "@/lib/utils";
import { scoreToPercent } from "@/lib/utils";

export function ScoreBar({
  value,
  showLabel = true,
  className,
}: {
  value?: number | null;
  showLabel?: boolean;
  className?: string;
}) {
  const pct = scoreToPercent(value);
  const tone =
    pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-red-400";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-2 w-full min-w-[60px] overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn("h-full rounded-full transition-all", tone)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className="w-9 shrink-0 text-right text-xs font-medium text-slate-600">
          {value === null || value === undefined ? "—" : pct}
        </span>
      )}
    </div>
  );
}
