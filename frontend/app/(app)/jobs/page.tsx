"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Briefcase, Plus, Search } from "lucide-react";

import { apiList } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDebounce, useFetch } from "@/lib/hooks";
import { useDomains } from "@/lib/meta";
import type { ListResponse, RequisitionListItem } from "@/lib/types";
import { REQUISITION_STATUSES } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";
import { PageHeader } from "@/components/common/page-header";
import { FilterBar } from "@/components/common/filter-bar";
import { DataTable, type Column } from "@/components/common/data-table";
import { EmptyState } from "@/components/common/states";
import { RequisitionStatusBadge } from "@/components/common/badges";
import { CreateJobModal } from "@/components/jobs/create-job-modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ALL = "__all__";
const LIMIT = 20;

function expRange(min?: number | null, max?: number | null) {
  if (min == null && max == null) return "Any";
  if (min != null && max != null) return `${min}–${max}y`;
  if (min != null) return `${min}y+`;
  return `≤${max}y`;
}

export default function JobsPage() {
  const router = useRouter();
  const { role } = useAuth();
  const canManage = role === "HR" || role === "DELIVERY_MANAGER" || role === "ADMIN";
  const { data: domains } = useDomains();

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(ALL);
  const [domainId, setDomainId] = useState(ALL);
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);

  const debSearch = useDebounce(search, 350);
  const query = useMemo(
    () => ({
      page,
      limit: LIMIT,
      search: debSearch || undefined,
      status: status === ALL ? undefined : status,
      domain_id: domainId === ALL ? undefined : domainId,
    }),
    [page, debSearch, status, domainId],
  );

  const { data, loading, error, reload } = useFetch<ListResponse<RequisitionListItem>>(
    (signal) => apiList<RequisitionListItem>("/requisitions", query, signal),
    [JSON.stringify(query)],
  );

  const rows = data?.data ?? [];
  const totalPages = data?.total_pages ?? 1;

  const columns: Column<RequisitionListItem>[] = [
    {
      key: "title",
      header: "Role",
      cell: (r) => (
        <div>
          <p className="text-sm font-medium">{r.title}</p>
          <p className="text-muted-foreground text-xs">{r.department ?? "—"}</p>
        </div>
      ),
    },
    { key: "domain", header: "Domain", cell: (r) => (r.domain ? <Badge variant="secondary">{r.domain}</Badge> : "—") },
    { key: "seniority", header: "Seniority", cell: (r) => titleCase(r.seniority_level) },
    { key: "location", header: "Location", cell: (r) => r.location ?? "—" },
    { key: "exp", header: "Experience", cell: (r) => expRange(r.min_experience_years, r.max_experience_years) },
    { key: "openings", header: "Openings", align: "right", cell: (r) => <span className="tabular-nums">{r.number_of_openings}</span> },
    { key: "status", header: "Status", cell: (r) => <RequisitionStatusBadge status={r.status} /> },
    { key: "created", header: "Created", align: "right", cell: (r) => <span className="text-muted-foreground text-xs">{formatDate(r.created_at)}</span> },
  ];

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Open requisitions and the roles you're hiring for."
        action={
          canManage && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" /> Create job
            </Button>
          )
        }
      />

      <FilterBar>
        <div className="relative min-w-[200px] flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search jobs…"
            className="border-0 bg-transparent pl-8 shadow-none focus-visible:ring-0"
          />
        </div>
        <Select value={status} onValueChange={(v) => { setStatus(v); setPage(1); }}>
          <SelectTrigger size="sm" className="w-auto min-w-[130px] border-0 bg-transparent shadow-none">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            {REQUISITION_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>{titleCase(s)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={domainId} onValueChange={(v) => { setDomainId(v); setPage(1); }}>
          <SelectTrigger size="sm" className="w-auto min-w-[130px] border-0 bg-transparent shadow-none">
            <SelectValue placeholder="Domain" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All domains</SelectItem>
            {(domains ?? []).map((d) => (
              <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        onRowClick={(r) => router.push(`/jobs/${r.id}`)}
        loading={loading}
        skeletonRows={10}
        empty={
          error ? (
            <EmptyState title="Couldn't load jobs" description={error} action={<Button variant="outline" onClick={reload}>Retry</Button>} />
          ) : (
            <EmptyState
              icon={<Briefcase className="size-6" />}
              title="No jobs found"
              description="Create your first requisition to start hiring."
              action={canManage ? <Button onClick={() => setCreateOpen(true)}><Plus className="size-4" /> Create job</Button> : undefined}
            />
          )
        }
      />

      {rows.length > 0 && (
        <div className="mt-4 flex items-center justify-between">
          <p className="text-muted-foreground text-sm">
            {data?.total ?? 0} jobs · page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      <CreateJobModal open={createOpen} onOpenChange={setCreateOpen} onCreated={reload} />
    </>
  );
}
