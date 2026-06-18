"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Briefcase } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [email, setEmail] = useState("hr@local.dev");
  const [password, setPassword] = useState("hr123");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already authenticated -> straight to dashboard.
  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      toast.success("Signed in successfully");
      router.replace("/dashboard");
    } catch (err) {
      const message = (err as Error).message || "Login failed";
      setError(message);
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 to-indigo-50 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600 text-white">
            <Briefcase className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-semibold text-slate-800">
            Recruitment ATS
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Sign in to your workspace
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <Input
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            error={error ?? undefined}
          />
          <Button
            type="submit"
            className="w-full"
            loading={submitting}
            size="lg"
          >
            Sign in
          </Button>
          <p className="text-center text-xs text-slate-400">
            Demo: hr@local.dev / hr123
          </p>
        </form>
      </div>
    </div>
  );
}
