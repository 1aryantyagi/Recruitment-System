"use client";

import { CheckCircle2, Clock, FileText, Percent } from "lucide-react";

import { OFFERS, type OfferRecord } from "@/lib/mock";
import { PageHeader } from "@/components/common/page-header";
import { KpiCard } from "@/components/common/kpi-card";
import { DataTable, type Column } from "@/components/common/data-table";
import { AvatarName } from "@/components/common/avatar-name";
import { Badge } from "@/components/ui/badge";

const STATUS_VARIANT: Record<OfferRecord["status"], "success" | "info" | "warning" | "destructive" | "muted"> = {
  Accepted: "success",
  Sent: "info",
  Negotiating: "warning",
  "Pending Approval": "warning",
  Declined: "destructive",
  Draft: "muted",
};

export default function OffersPage() {
  const sent = OFFERS.filter((o) => o.sentOn).length;
  const accepted = OFFERS.filter((o) => o.status === "Accepted").length;
  const pending = OFFERS.filter((o) => o.status === "Pending Approval" || o.status === "Negotiating").length;
  const acceptanceRate = sent ? Math.round((accepted / sent) * 100) : 0;

  const columns: Column<OfferRecord>[] = [
    { key: "candidate", header: "Candidate", cell: (o) => <AvatarName name={o.candidate} subtitle={o.role} hue={o.avatarHue} /> },
    { key: "status", header: "Status", cell: (o) => <Badge variant={STATUS_VARIANT[o.status]}>{o.status}</Badge> },
    { key: "ctc", header: "Package", align: "right", cell: (o) => <span className="font-medium tabular-nums">{o.ctc}</span> },
    { key: "sent", header: "Sent", cell: (o) => o.sentOn ?? <span className="text-muted-foreground">—</span> },
    { key: "approver", header: "Approval", cell: (o) => <Badge variant="muted">{o.approver}</Badge> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Preview · sample data"
        title="Offers"
        description="Offer creation, approvals, and acceptance tracking."
      />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Offers sent" value={sent} icon={FileText} accent="primary" />
        <KpiCard label="Accepted" value={accepted} icon={CheckCircle2} accent="emerald" />
        <KpiCard label="Pending" value={pending} icon={Clock} accent="amber" />
        <KpiCard label="Acceptance rate" value={`${acceptanceRate}%`} icon={Percent} accent="violet" />
      </div>
      <DataTable columns={columns} rows={OFFERS} getRowId={(o) => o.id} />
    </>
  );
}
