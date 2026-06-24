import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A compact label / value pair used across detail panels. */
export function Stat({
  label,
  value,
  icon,
  className,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-0.5", className)}>
      <div className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
        {icon}
        {label}
      </div>
      <div className="text-sm font-medium tabular-nums" data-slot="metric">
        {value ?? "—"}
      </div>
    </div>
  );
}
