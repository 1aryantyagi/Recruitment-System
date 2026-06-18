import type { HTMLAttributes, ReactNode, ThHTMLAttributes, TdHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Table({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full border-collapse text-sm", className)}>
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead className="border-b border-slate-200 bg-slate-50/70 text-left">
      {children}
    </thead>
  );
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-slate-100">{children}</tbody>;
}

export function TR({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={cn("transition", className)} {...props}>
      {children}
    </tr>
  );
}

export function TH({
  className,
  children,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "whitespace-nowrap px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500",
        className,
      )}
      {...props}
    >
      {children}
    </th>
  );
}

export function TD({
  className,
  children,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn("px-4 py-3 text-slate-700", className)} {...props}>
      {children}
    </td>
  );
}
