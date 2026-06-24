"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  LogOut,
  Menu,
  PanelLeft,
  Search,
  Settings,
  Sparkles,
  UserRound,
} from "lucide-react";

import { useAuth } from "@/lib/auth";
import { navItemForPath } from "@/lib/nav";
import { cn, initials, titleCase } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeToggle } from "./theme-toggle";

const MOCK_NOTIFICATIONS = [
  { id: 1, title: "5 new candidates matched", detail: "Senior Backend Engineer", time: "12m", unread: true },
  { id: 2, title: "Interview feedback pending", detail: "Mei Lin · Technical round", time: "1h", unread: true },
  { id: 3, title: "Offer approved", detail: "Ananya Gupta · Frontend Lead", time: "3h", unread: false },
];

export function Topbar({
  onMenu,
  onToggleCollapse,
  onSearch,
  onAssistant,
}: {
  onMenu: () => void;
  onToggleCollapse: () => void;
  onSearch: () => void;
  onAssistant: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const current = navItemForPath(pathname);
  const unread = MOCK_NOTIFICATIONS.filter((n) => n.unread).length;

  return (
    <header className="bg-background/80 sticky top-0 z-20 flex h-16 items-center gap-3 border-b px-4 backdrop-blur-md lg:px-6">
      <Button
        variant="ghost"
        size="icon-sm"
        className="lg:hidden"
        onClick={onMenu}
        aria-label="Open navigation"
      >
        <Menu className="size-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        className="hidden lg:inline-flex"
        onClick={onToggleCollapse}
        aria-label="Collapse sidebar"
      >
        <PanelLeft className="size-4" />
      </Button>

      <div className="hidden min-w-0 md:block">
        <h1 className="truncate text-sm font-semibold">
          {current?.label ?? "Talent OS"}
        </h1>
      </div>

      {/* Global search */}
      <button
        onClick={onSearch}
        className="text-muted-foreground bg-muted/50 hover:bg-muted ml-auto flex h-9 w-full max-w-xs items-center gap-2 rounded-lg border px-3 text-sm transition-colors"
      >
        <Search className="size-4" />
        <span className="hidden sm:inline">Search…</span>
        <kbd className="bg-background text-muted-foreground ml-auto hidden rounded border px-1.5 py-0.5 font-mono text-[10px] sm:inline">
          ⌘K
        </kbd>
      </button>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onAssistant}
          aria-label="AI assistant"
          className="text-primary"
        >
          <Sparkles className="size-4" />
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Notifications" className="relative">
              <Bell className="size-4" />
              {unread > 0 && (
                <span className="bg-primary absolute top-1.5 right-1.5 size-1.5 rounded-full" />
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80">
            <div className="flex items-center justify-between px-2 py-1.5">
              <span className="text-sm font-semibold">Notifications</span>
              <Badge variant="muted" className="text-[10px]">
                {unread} new
              </Badge>
            </div>
            <DropdownMenuSeparator />
            {MOCK_NOTIFICATIONS.map((n) => (
              <DropdownMenuItem key={n.id} className="flex-col items-start gap-0.5 py-2">
                <div className="flex w-full items-center gap-2">
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      n.unread ? "bg-primary" : "bg-transparent",
                    )}
                  />
                  <span className="text-sm font-medium">{n.title}</span>
                  <span className="text-muted-foreground ml-auto text-xs">{n.time}</span>
                </div>
                <span className="text-muted-foreground pl-3.5 text-xs">{n.detail}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <ThemeToggle />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="ml-1 flex items-center gap-2 rounded-full outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40">
              <Avatar className="size-8">
                <AvatarFallback className="bg-primary/12 text-primary text-xs font-semibold">
                  {initials(user?.name)}
                </AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="text-foreground">
              <div className="flex flex-col">
                <span className="text-sm font-semibold">{user?.name}</span>
                <span className="text-muted-foreground text-xs font-normal">
                  {user?.email}
                </span>
                {user?.role && (
                  <Badge variant="muted" className="mt-1.5 w-fit text-[10px]">
                    {titleCase(user.role)}
                  </Badge>
                )}
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => router.push("/settings")}>
              <UserRound className="size-4" /> Profile
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings")}>
              <Settings className="size-4" /> Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={logout}>
              <LogOut className="size-4" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
