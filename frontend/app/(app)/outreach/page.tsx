"use client";

import { Mail, MessageSquareReply, Send, TrendingUp } from "lucide-react";

import { OUTREACH_CAMPAIGNS, type OutreachCampaign } from "@/lib/mock";
import { PageHeader } from "@/components/common/page-header";
import { KpiCard } from "@/components/common/kpi-card";
import { DataTable, type Column } from "@/components/common/data-table";
import { Badge } from "@/components/ui/badge";

const STATUS_VARIANT: Record<OutreachCampaign["status"], "success" | "warning" | "muted" | "secondary"> = {
  Active: "success",
  Paused: "warning",
  Draft: "muted",
  Completed: "secondary",
};

export default function OutreachPage() {
  const active = OUTREACH_CAMPAIGNS.filter((c) => c.status === "Active");
  const avg = (key: "openRate" | "replyRate" | "conversionRate") => {
    const sent = OUTREACH_CAMPAIGNS.filter((c) => c.sent > 0);
    return Math.round(sent.reduce((a, c) => a + c[key], 0) / Math.max(1, sent.length));
  };

  const columns: Column<OutreachCampaign>[] = [
    {
      key: "name",
      header: "Campaign",
      cell: (c) => (
        <div>
          <p className="text-sm font-medium">{c.name}</p>
          <p className="text-muted-foreground text-xs">{c.role}</p>
        </div>
      ),
    },
    { key: "channel", header: "Channel", cell: (c) => <Badge variant="muted">{c.channel}</Badge> },
    { key: "status", header: "Status", cell: (c) => <Badge variant={STATUS_VARIANT[c.status]}>{c.status}</Badge> },
    { key: "sent", header: "Sent", align: "right", cell: (c) => <span className="tabular-nums">{c.sent}</span> },
    { key: "open", header: "Open", align: "right", cell: (c) => <span className="tabular-nums">{c.openRate}%</span> },
    { key: "reply", header: "Reply", align: "right", cell: (c) => <span className="tabular-nums">{c.replyRate}%</span> },
    { key: "conv", header: "Conversion", align: "right", cell: (c) => <span className="font-medium tabular-nums">{c.conversionRate}%</span> },
    { key: "updated", header: "Updated", align: "right", cell: (c) => <span className="text-muted-foreground text-xs">{c.updated}</span> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Preview · sample data"
        title="Outreach Campaigns"
        description="Multi-channel candidate outreach with AI-personalized messaging."
      />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Avg open rate" value={`${avg("openRate")}%`} icon={Mail} accent="primary" />
        <KpiCard label="Avg reply rate" value={`${avg("replyRate")}%`} icon={MessageSquareReply} accent="emerald" />
        <KpiCard label="Avg conversion" value={`${avg("conversionRate")}%`} icon={TrendingUp} accent="violet" />
        <KpiCard label="Active campaigns" value={active.length} icon={Send} accent="amber" />
      </div>
      <DataTable columns={columns} rows={OUTREACH_CAMPAIGNS} getRowId={(c) => c.id} />
    </>
  );
}
