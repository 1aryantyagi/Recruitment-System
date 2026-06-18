"use client";

import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ className, label, error, id, ...props }, ref) {
    const areaId = id ?? props.name;
    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={areaId}
            className="mb-1 block text-xs font-medium text-slate-600"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={areaId}
          className={cn(
            "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 transition focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-50",
            error && "border-red-400",
            className,
          )}
          rows={props.rows ?? 4}
          {...props}
        />
        {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      </div>
    );
  },
);
