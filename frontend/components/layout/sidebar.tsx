"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sparkles } from "lucide-react";

import { NAV_SECTIONS } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function SidebarBrand({ collapsed }: { collapsed?: boolean }) {
  return (
    <Link
      href="/dashboard"
      className="flex h-16 items-center gap-2.5 px-4 outline-none"
    >
      <div className="bg-primary text-primary-foreground flex size-9 shrink-0 items-center justify-center rounded-xl shadow-sm">
        <Sparkles className="size-5" />
      </div>
      {!collapsed && (
        <div className="leading-tight">
          <p className="text-sm font-semibold tracking-tight">Talent OS</p>
          <p className="text-muted-foreground text-[10px] font-medium tracking-wider uppercase">
            AI Recruitment
          </p>
        </div>
      )}
    </Link>
  );
}

export function SidebarNav({
  collapsed,
  onNavigate,
}: {
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-5 overflow-y-auto px-3 py-2">
      {NAV_SECTIONS.map((section) => (
        <div key={section.title} className="flex flex-col gap-1">
          {!collapsed && (
            <p className="text-muted-foreground px-2 pb-1 text-[10px] font-semibold tracking-wider uppercase">
              {section.title}
            </p>
          )}
          {section.items.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;
            const link = (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors outline-none",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                )}
              >
                {active && (
                  <span className="bg-primary absolute left-0 h-5 w-0.5 rounded-r-full" />
                )}
                <Icon className="size-[18px] shrink-0" />
                {!collapsed && (
                  <>
                    <span className="truncate">{item.label}</span>
                    {item.soon && (
                      <Badge variant="muted" className="ml-auto px-1.5 py-0 text-[10px]">
                        Soon
                      </Badge>
                    )}
                  </>
                )}
              </Link>
            );
            if (collapsed) {
              return (
                <Tooltip key={item.href}>
                  <TooltipTrigger asChild>{link}</TooltipTrigger>
                  <TooltipContent side="right">{item.label}</TooltipContent>
                </Tooltip>
              );
            }
            return link;
          })}
        </div>
      ))}
    </nav>
  );
}
