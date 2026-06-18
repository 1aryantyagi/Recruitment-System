"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toast: (message: string, variant?: ToastVariant) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

let counter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, variant: ToastVariant = "info") => {
      const id = ++counter;
      setToasts((prev) => [...prev, { id, message, variant }]);
      setTimeout(() => remove(id), 5000);
    },
    [remove],
  );

  const value: ToastContextValue = {
    toast,
    success: (m) => toast(m, "success"),
    error: (m) => toast(m, "error"),
    info: (m) => toast(m, "info"),
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <ToastCard key={t.id} item={t} onClose={() => remove(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({
  item,
  onClose,
}: {
  item: ToastItem;
  onClose: () => void;
}) {
  const Icon =
    item.variant === "success"
      ? CheckCircle2
      : item.variant === "error"
        ? AlertCircle
        : Info;
  return (
    <div
      role="alert"
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-lg border bg-white p-3 shadow-lg",
        item.variant === "success" && "border-emerald-200",
        item.variant === "error" && "border-red-200",
        item.variant === "info" && "border-slate-200",
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 h-5 w-5 shrink-0",
          item.variant === "success" && "text-emerald-600",
          item.variant === "error" && "text-red-600",
          item.variant === "info" && "text-slate-500",
        )}
      />
      <p className="flex-1 text-sm text-slate-700">{item.message}</p>
      <button
        onClick={onClose}
        className="text-slate-400 transition hover:text-slate-600"
        aria-label="Dismiss"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
