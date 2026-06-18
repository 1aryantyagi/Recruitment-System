"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabDef {
  key: string;
  label: ReactNode;
  count?: number;
}

export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (key: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("border-b border-slate-200", className)}>
      <nav className="-mb-px flex gap-1 overflow-x-auto">
        {tabs.map((tab) => {
          const isActive = tab.key === active;
          return (
            <button
              key={tab.key}
              onClick={() => onChange(tab.key)}
              className={cn(
                "flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition",
                isActive
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700",
              )}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-0.5 text-xs",
                    isActive
                      ? "bg-indigo-100 text-indigo-700"
                      : "bg-slate-100 text-slate-500",
                  )}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
