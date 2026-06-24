import {
  LayoutDashboard,
  Users,
  Briefcase,
  Columns3,
  UserSearch,
  FileText,
  CalendarClock,
  ClipboardCheck,
  Bot,
  Send,
  BarChart3,
  UsersRound,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Mock-only preview page (no backend yet). */
  soon?: boolean;
  adminOnly?: boolean;
  /** Keywords to boost in the command palette. */
  keywords?: string[];
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Overview",
    items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    title: "Recruiting",
    items: [
      { href: "/candidates", label: "Candidates", icon: Users, keywords: ["people", "talent", "applicants"] },
      { href: "/jobs", label: "Jobs", icon: Briefcase, keywords: ["requisitions", "roles", "openings"] },
      { href: "/pipeline", label: "ATS Pipeline", icon: Columns3, keywords: ["kanban", "board", "stages"] },
      { href: "/talent-pool", label: "Talent Pool", icon: UserSearch, soon: true, keywords: ["sourcing", "passive"] },
      { href: "/offers", label: "Offers", icon: FileText, soon: true, keywords: ["offer", "compensation"] },
    ],
  },
  {
    title: "Interviewing",
    items: [
      { href: "/interviews", label: "Interviews", icon: CalendarClock, keywords: ["calendar", "schedule", "rounds"] },
      { href: "/evaluations", label: "Evaluations", icon: ClipboardCheck, keywords: ["feedback", "scorecards", "ratings"] },
    ],
  },
  {
    title: "Automation",
    items: [
      { href: "/agents", label: "AI Agents", icon: Bot, keywords: ["automation", "screening", "ai"] },
      { href: "/outreach", label: "Outreach", icon: Send, soon: true, keywords: ["campaigns", "email", "sequences"] },
    ],
  },
  {
    title: "Insights",
    items: [{ href: "/analytics", label: "Hiring Analytics", icon: BarChart3, keywords: ["reports", "metrics", "funnel"] }],
  },
  {
    title: "Workspace",
    items: [
      { href: "/team", label: "Team", icon: UsersRound, keywords: ["users", "interviewers", "members"] },
      { href: "/settings", label: "Settings", icon: Settings, keywords: ["integrations", "skills", "gmail", "profile"] },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);

export function navItemForPath(pathname: string): NavItem | undefined {
  return NAV_ITEMS.find(
    (i) => pathname === i.href || pathname.startsWith(i.href + "/"),
  );
}
