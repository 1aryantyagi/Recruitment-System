import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A toolbar container for search + filters above a table or board. */
export function FilterBar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-card mb-4 flex flex-wrap items-center gap-2 rounded-xl border p-2 shadow-card",
        className,
      )}
    >
      {children}
    </div>
  );
}
