import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white shadow-sm",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4",
        className,
      )}
    >
      <div>
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {description && (
          <p className="mt-0.5 text-xs text-slate-500">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export function CardBody({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("p-5", className)} {...props}>
      {children}
    </div>
  );
}
