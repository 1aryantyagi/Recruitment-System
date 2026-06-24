import { cn, scoreToPercent } from "@/lib/utils";
import { scoreColor } from "@/lib/labels";

/** Circular score ring (0–1 or 0–100 input). */
export function ScoreRing({
  score,
  size = 44,
  strokeWidth = 4,
  className,
  showValue = true,
}: {
  score?: number | null;
  size?: number;
  strokeWidth?: number;
  className?: string;
  showValue?: boolean;
}) {
  const pct = scoreToPercent(score);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  const color = scoreColor(pct);

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
          className="stroke-muted fill-none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={cn("fill-none transition-all duration-700 ease-out", color)}
          stroke="currentColor"
        />
      </svg>
      {showValue && (
        <span
          className={cn(
            "absolute inset-0 flex items-center justify-center text-[11px] font-semibold tabular-nums",
            color,
          )}
        >
          {score === null || score === undefined ? "—" : pct}
        </span>
      )}
    </div>
  );
}

/** Horizontal score bar with label. */
export function ScoreBar({
  score,
  label,
  className,
}: {
  score?: number | null;
  label?: string;
  className?: string;
}) {
  const pct = scoreToPercent(score);
  const color = scoreColor(pct);
  return (
    <div className={cn("space-y-1", className)}>
      {label && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{label}</span>
          <span className={cn("font-semibold tabular-nums", color)}>{pct}</span>
        </div>
      )}
      <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
        <div
          className={cn("h-full rounded-full transition-all duration-700", color)}
          style={{ width: `${pct}%`, backgroundColor: "currentColor" }}
        />
      </div>
    </div>
  );
}
