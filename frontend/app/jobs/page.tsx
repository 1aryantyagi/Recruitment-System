"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { AppShell, PageHeader } from "@/components/AppShell";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { StatusBadge, Badge } from "@/components/ui/Badge";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/Table";
import { Pagination } from "@/components/ui/Pagination";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/Spinner";
import { CreateJobModal } from "@/components/jobs/CreateJobModal";
import { useAuth } from "@/lib/auth";
import { apiList } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import { useDomains } from "@/lib/meta";
import { formatNumber, titleCase, formatDate } from "@/lib/utils";
import {
  REQUISITION_STATUSES,
  type RequisitionListItem,
} from "@/lib/types";

const LIMIT = 20;

export default function JobsPage() {
  return (
    <AppShell>
      <JobsContent />
    </AppShell>
  );
}

function JobsContent() {
  const router = useRouter();
  const { isHR, isDeliveryManager, isAdmin } = useAuth();
  const { data: domains } = useDomains();
  const canCreate = isHR || isDeliveryManager || isAdmin;

  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [domainId, setDomainId] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const query = useMemo(
    () => ({
      page,
      limit: LIMIT,
      status: status || undefined,
      domain_id: domainId || undefined,
    }),
    [page, status, domainId],
  );

  const { data, loading, error, reload } = useFetch(
    (signal) =>
      apiList<RequisitionListItem>("/requisitions", query as never, signal),
    [JSON.stringify(query)],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Jobs"
        description="Open and historical requisitions"
        action={
          canCreate ? (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> Create job
            </Button>
          ) : undefined
        }
      />

      <Card className="p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select
            label="Status"
            options={REQUISITION_STATUSES.map((s) => ({
              value: s,
              label: titleCase(s),
            }))}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            placeholder="Any status"
          />
          <Select
            label="Domain"
            options={(domains ?? []).map((d) => ({
              value: d.id,
              label: d.name,
            }))}
            value={domainId}
            onChange={(e) => {
              setDomainId(e.target.value);
              setPage(1);
            }}
            placeholder="Any domain"
          />
        </div>
      </Card>

      <Card>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : !data || data.data.length === 0 ? (
          <EmptyState title="No requisitions found" />
        ) : (
          <>
            <Table>
              <THead>
                <TR>
                  <TH>Title</TH>
                  <TH>Domain</TH>
                  <TH>Seniority</TH>
                  <TH>Location</TH>
                  <TH>Experience</TH>
                  <TH>Openings</TH>
                  <TH>Status</TH>
                  <TH>Created</TH>
                </TR>
              </THead>
              <TBody>
                {data.data.map((r) => (
                  <TR
                    key={r.id}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() => router.push(`/jobs/${r.id}`)}
                  >
                    <TD>
                      <div className="font-medium text-slate-800">
                        {r.title}
                      </div>
                      {r.department && (
                        <p className="text-xs text-slate-400">{r.department}</p>
                      )}
                    </TD>
                    <TD>{r.domain ?? "—"}</TD>
                    <TD>
                      {r.seniority_level ? (
                        <Badge tone="purple">
                          {titleCase(r.seniority_level)}
                        </Badge>
                      ) : (
                        "—"
                      )}
                    </TD>
                    <TD>
                      {r.location ?? "—"}
                      {r.work_mode && (
                        <span className="ml-1 text-xs text-slate-400">
                          ({titleCase(r.work_mode)})
                        </span>
                      )}
                    </TD>
                    <TD>
                      {r.min_experience_years != null ||
                      r.max_experience_years != null
                        ? `${r.min_experience_years ?? 0}–${
                            r.max_experience_years ?? "+"
                          } yrs`
                        : "—"}
                    </TD>
                    <TD>{formatNumber(r.number_of_openings)}</TD>
                    <TD>
                      <StatusBadge status={r.status} />
                    </TD>
                    <TD className="text-xs text-slate-400">
                      {formatDate(r.created_at)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination
              page={data.page}
              totalPages={data.total_pages}
              total={data.total}
              onPageChange={setPage}
            />
          </>
        )}
      </Card>

      <CreateJobModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={reload}
      />
    </div>
  );
}
