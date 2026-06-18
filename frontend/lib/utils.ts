import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatNumber(value?: number | null, fractionDigits = 0): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: fractionDigits,
  });
}

export function formatCurrency(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString(undefined, {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  });
}

export function formatPercent(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  // Server values may be 0-1 or 0-100; normalise heuristically.
  const v = value <= 1 ? value * 100 : value;
  return `${v.toFixed(1)}%`;
}

/** Convert a 0-1 or 0-100 score to a 0-100 percentage number. */
export function scoreToPercent(value?: number | null): number {
  if (value === null || value === undefined) return 0;
  const v = value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, Math.round(v)));
}

export function titleCase(value?: string | null): string {
  if (!value) return "—";
  return value
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}
