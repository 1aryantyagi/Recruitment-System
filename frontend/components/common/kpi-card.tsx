import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, type LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface KpiCardProps {
  label: string;
  value: ReactNode;
  icon?: LucideIcon;
  /** e.g. "+12%" or "-3%" */
  delta?: string;
  deltaDirection?: "up" | "down" | "neutral";
  hint?: string;
  accent?: "primary" | "emerald" | "amber" | "rose" | "violet";
  className?: string;
  style?: React.CSSProperties;
}

const ACCENTS: Record<NonNullable<KpiCardProps["accent"]>, string> = {
  primary: "text-primary bg-primary/10",
  emerald: "text-emerald-600 bg-emerald-500/10 dark:text-emerald-400",
  amber: "text-amber-600 bg-amber-500/10 dark:text-amber-400",
  rose: "text-rose-600 bg-rose-500/10 dark:text-rose-400",
  violet: "text-violet-600 bg-violet-500/10 dark:text-violet-400",
};

export function KpiCard({
  label,
  value,
  icon: Icon,
  delta,
  deltaDirection = "neutral",
  hint,
  accent = "primary",
  className,
  style,
}: KpiCardProps) {
  return (
    <Card
      className={cn(
        "animate-in fade-in slide-in-from-bottom-1 gap-0 p-5 duration-500",
        className,
      )}
      style={style}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-muted-foreground text-sm font-medium">{label}</span>
        {Icon && (
          <span
            className={cn(
              "flex size-8 items-center justify-center rounded-lg",
              ACCENTS[accent],
            )}
          >
            <Icon className="size-4" />
          </span>
        )}
      </div>
      <div className="mt-3 flex items-end justify-between gap-2">
        <span
          className="text-3xl font-semibold tracking-tight tabular-nums"
          data-slot="metric"
        >
          {value}
        </span>
        {delta && (
          <span
            className={cn(
              "mb-1 inline-flex items-center gap-0.5 text-xs font-medium",
              deltaDirection === "up" && "text-emerald-600 dark:text-emerald-400",
              deltaDirection === "down" && "text-rose-600 dark:text-rose-400",
              deltaDirection === "neutral" && "text-muted-foreground",
            )}
          >
            {deltaDirection === "up" && <ArrowUpRight className="size-3" />}
            {deltaDirection === "down" && <ArrowDownRight className="size-3" />}
            {delta}
          </span>
        )}
      </div>
      {hint && <p className="text-muted-foreground mt-1 text-xs">{hint}</p>}
    </Card>
  );
}
