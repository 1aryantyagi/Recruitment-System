"use client";

import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, label, hint, error, leftIcon, id, ...props },
  ref,
) {
  const inputId = id ?? props.name;
  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="mb-1 block text-xs font-medium text-slate-600"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
            {leftIcon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-800 placeholder:text-slate-400 transition focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-50",
            leftIcon && "pl-9",
            error && "border-red-400 focus:border-red-400 focus:ring-red-100",
            className,
          )}
          {...props}
        />
      </div>
      {error ? (
        <p className="mt-1 text-xs text-red-600">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-slate-400">{hint}</p>
      ) : null}
    </div>
  );
});
