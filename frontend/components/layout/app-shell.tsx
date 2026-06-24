"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { useRequireAuth } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { LoadingState } from "@/components/common/states";
import { SidebarBrand, SidebarNav } from "./sidebar";
import { Topbar } from "./topbar";
import { CommandPalette } from "./command-palette";
import { AiAssistant, AiAssistantFab } from "./ai-assistant";

export function AppShell({ children }: { children: ReactNode }) {
  const { loading, authed } = useRequireAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);

  // Restore desktop collapse preference.
  useEffect(() => {
    setCollapsed(localStorage.getItem("sidebar-collapsed") === "1");
  }, []);
  const toggleCollapse = useCallback(() => {
    setCollapsed((c) => {
      localStorage.setItem("sidebar-collapsed", c ? "0" : "1");
      return !c;
    });
  }, []);

  // ⌘K / Ctrl-K opens the command palette.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdkOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingState label="Loading your workspace…" />
      </div>
    );
  }
  if (!authed) return null; // useRequireAuth redirects

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside
        className={cn(
          "bg-sidebar border-sidebar-border sticky top-0 hidden h-screen shrink-0 flex-col border-r transition-[width] duration-200 lg:flex",
          collapsed ? "w-[68px]" : "w-64",
        )}
      >
        <SidebarBrand collapsed={collapsed} />
        <div className="min-h-0 flex-1 overflow-y-auto">
          <SidebarNav collapsed={collapsed} />
        </div>
      </aside>

      {/* Mobile sidebar */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="bg-sidebar w-72 p-0">
          <SidebarBrand />
          <div className="min-h-0 flex-1 overflow-y-auto">
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          onMenu={() => setMobileOpen(true)}
          onToggleCollapse={toggleCollapse}
          onSearch={() => setCmdkOpen(true)}
          onAssistant={() => setAssistantOpen(true)}
        />
        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 lg:px-8">
          {children}
        </main>
      </div>

      <CommandPalette open={cmdkOpen} onOpenChange={setCmdkOpen} />
      <AiAssistant open={assistantOpen} onOpenChange={setAssistantOpen} />
      <AiAssistantFab onClick={() => setAssistantOpen(true)} />
    </div>
  );
}
