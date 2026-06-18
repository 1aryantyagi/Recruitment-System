"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";
import { LoadingState } from "@/components/ui/Spinner";

export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    if (getToken()) {
      router.replace("/dashboard");
    } else {
      router.replace("/login");
    }
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <LoadingState label="Redirecting…" />
    </div>
  );
}
