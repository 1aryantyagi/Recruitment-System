"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Briefcase,
  CalendarClock,
  BarChart3,
  Shield,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useRequireAuth } from "@/lib/hooks";
import { cn, initials, titleCase } from "@/lib/utils";
import { LoadingState } from "@/components/ui/Spinner";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  adminOnly?: boolean;
}

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/candidates", label: "Candidates", icon: Users },
  { href: "/jobs", label: "Jobs", icon: Briefcase },
  { href: "/interviews", label: "Interviews", icon: CalendarClock },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/admin", label: "Admin", icon: Shield, adminOnly: true },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, authed } = useRequireAuth();
  const { logout, isAdmin } = useAuth();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <LoadingState label="Loading your workspace…" />
      </div>
    );
  }

  if (!authed || !user) {
    // useRequireAuth handles the redirect; render nothing meanwhile.
    return null;
  }

  const items = NAV.filter((n) => !n.adminOnly || isAdmin);

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-800">
      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 transform border-r border-slate-200 bg-white transition-transform lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center gap-2 border-b border-slate-100 px-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            AT
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-800">ATS</p>
            <p className="text-[10px] uppercase tracking-wider text-slate-400">
              Recruitment
            </p>
          </div>
        </div>
        <nav className="flex flex-col gap-1 p-3">
          {items.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                  active
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                )}
              >
                <Icon className="h-5 w-5" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/30 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur lg:px-6">
          <div className="flex items-center gap-3">
            <button
              className="rounded-md p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
              onClick={() => setMobileOpen((o) => !o)}
              aria-label="Toggle navigation"
            >
              {mobileOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </button>
            <h1 className="text-sm font-semibold text-slate-700">
              {items.find(
                (i) =>
                  pathname === i.href || pathname.startsWith(i.href + "/"),
              )?.label ?? "ATS"}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-slate-700">{user.name}</p>
              <p className="text-[11px] text-slate-400">
                {titleCase(user.role)}
              </p>
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">
              {initials(user.name)}
            </div>
            <button
              onClick={logout}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">{title}</h2>
        {description && (
          <p className="mt-0.5 text-sm text-slate-500">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
