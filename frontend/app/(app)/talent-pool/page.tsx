"use client";

import { useState } from "react";
import { UserSearch } from "lucide-react";

import { SOURCED_CANDIDATES, type SourcedCandidate } from "@/lib/mock";
import { PageHeader } from "@/components/common/page-header";
import { KpiCard } from "@/components/common/kpi-card";
import { ScoreRing } from "@/components/common/score";
import { InitialsAvatar } from "@/components/common/avatar-name";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const OUTREACH_VARIANT: Record<SourcedCandidate["outreach"], "success" | "info" | "warning" | "muted"> = {
  Responded: "success",
  "In pipeline": "info",
  Contacted: "warning",
  "Not contacted": "muted",
};

const SOURCES = ["All", "LinkedIn", "GitHub", "Referral", "Job Board", "Internal DB"];

export default function TalentPoolPage() {
  const [source, setSource] = useState("All");
  const rows = source === "All" ? SOURCED_CANDIDATES : SOURCED_CANDIDATES.filter((c) => c.source === source);

  const responded = SOURCED_CANDIDATES.filter((c) => c.outreach === "Responded").length;
  const inPipeline = SOURCED_CANDIDATES.filter((c) => c.outreach === "In pipeline").length;
  const avgMatch = Math.round(SOURCED_CANDIDATES.reduce((a, c) => a + c.matchScore, 0) / SOURCED_CANDIDATES.length);

  return (
    <>
      <PageHeader
        eyebrow="Preview · sample data"
        title="Talent Pool"
        description="Passive candidates sourced from across the web and your network."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Sourced" value={SOURCED_CANDIDATES.length} icon={UserSearch} accent="violet" />
        <KpiCard label="Responded" value={responded} accent="emerald" />
        <KpiCard label="In pipeline" value={inPipeline} accent="primary" />
        <KpiCard label="Avg match" value={`${avgMatch}`} accent="amber" />
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5">
        {SOURCES.map((s) => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${source === s ? "border-primary bg-primary/10 text-primary" : "bg-muted/50 hover:bg-muted text-muted-foreground"}`}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((c) => (
          <Card key={c.id} className="gap-3 p-5">
            <div className="flex items-start gap-3">
              <InitialsAvatar name={c.name} hue={c.avatarHue} size="lg" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{c.name}</p>
                <p className="text-muted-foreground truncate text-xs">{c.title} · {c.company}</p>
                <p className="text-muted-foreground text-xs">{c.location}</p>
              </div>
              <ScoreRing score={c.matchScore} size={44} />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {c.skills.map((s) => <Badge key={s} variant="muted">{s}</Badge>)}
            </div>
            <div className="flex items-center justify-between border-t pt-3">
              <Badge variant="outline">{c.source}</Badge>
              <Badge variant={OUTREACH_VARIANT[c.outreach]}>{c.outreach}</Badge>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
