"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowRight,
  BarChart3,
  Bot,
  CalendarClock,
  Loader2,
  Users,
} from "lucide-react";

import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/logo/logo";

const DEMO = [
  { label: "HR", email: "hr@local.dev", password: "hr123" },
  { label: "Admin", email: "admin@local.dev", password: "admin123" },
  { label: "Manager", email: "dm@local.dev", password: "dm123" },
];

const HIGHLIGHTS = [
  { icon: Bot, title: "11 AI agents", text: "Screen, score, schedule, and evaluate — automatically." },
  { icon: Users, title: "Unified ATS", text: "Every candidate, job, and interview in one pipeline." },
  { icon: CalendarClock, title: "Smart scheduling", text: "Conversational booking and calendar sync." },
  { icon: BarChart3, title: "Hiring analytics", text: "Funnel, sources, and time-to-hire at a glance." },
];

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("hr@local.dev");
  const [password, setPassword] = useState("hr123");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back");
      router.replace("/dashboard");
    } catch (err) {
      toast.error((err as Error).message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel */}
      <div className="bg-primary text-primary-foreground relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="bg-grid absolute inset-0 opacity-20" />
        <Logo priority tone="onPrimary" className="relative" />

        <div className="relative max-w-md">
          <h1 className="text-3xl font-semibold tracking-tight">
            The AI recruitment operating system.
          </h1>
          <p className="text-primary-foreground/80 mt-3 text-sm">
            Hire faster with a multi-agent ATS that screens resumes, books
            interviews, and surfaces the best candidates for every role.
          </p>
          <div className="mt-8 grid grid-cols-2 gap-4">
            {HIGHLIGHTS.map((h) => (
              <div key={h.title} className="bg-primary-foreground/10 rounded-xl border border-white/10 p-4 backdrop-blur">
                <h.icon className="mb-2 size-5" />
                <p className="text-sm font-medium">{h.title}</p>
                <p className="text-primary-foreground/70 mt-0.5 text-xs">{h.text}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="text-primary-foreground/60 relative text-xs">
          © {new Date().getFullYear()} Talent OS · Internal recruitment platform
        </p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm">
          <Logo priority className="mb-8 lg:hidden" />

          <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Welcome back. Enter your credentials to continue.
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <>
                  Sign in <ArrowRight className="size-4" />
                </>
              )}
            </Button>
          </form>

          <div className="mt-8">
            <p className="text-muted-foreground mb-2 text-xs font-medium">
              Demo accounts
            </p>
            <div className="flex flex-wrap gap-2">
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  type="button"
                  onClick={() => {
                    setEmail(d.email);
                    setPassword(d.password);
                  }}
                  className="bg-muted/60 hover:bg-muted rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors"
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
