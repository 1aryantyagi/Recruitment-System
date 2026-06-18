"use client";

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, PhoneCall, CalendarPlus, Pencil } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { Input } from "@/components/ui/Input";
import { ScoreBar } from "@/components/ui/ScoreBar";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/Table";
import { Pagination } from "@/components/ui/Pagination";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/Spinner";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { ScheduleInterviewModal } from "@/components/interviews/ScheduleInterviewModal";
import { useAuth } from "@/lib/auth";
import { apiGet, apiList, apiPatch, apiPost } from "@/lib/api";
import { useFetch, useDebounce } from "@/lib/hooks";
import {
  formatCurrency,
  formatDate,
  formatNumber,
  titleCase,
} from "@/lib/utils";
import {
  REQUISITION_STATUSES,
  type CandidateListItem,
  type RequisitionDetail,
} from "@/lib/types";

const LIMIT = 20;

export default function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <AppShell>
      <JobContent id={id} />
    </AppShell>
  );
}

function JobContent({ id }: { id: string }) {
  const { isHR, isDeliveryManager, isAdmin, canManageCandidates } = useAuth();
  const toast = useToast();
  const canEdit = isHR || isDeliveryManager || isAdmin;

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusOpen, setStatusOpen] = useState(false);
  const [scheduleFor, setScheduleFor] = useState<string | null>(null);
  const debouncedSearch = useDebounce(search);

  const {
    data: req,
    loading,
    error,
    reload,
  } = useFetch<RequisitionDetail>(
    () => apiGet<RequisitionDetail>(`/requisitions/${id}`),
    [id],
  );

  const candQuery = useMemo(
    () => ({ page, limit: LIMIT, search: debouncedSearch || undefined }),
    [page, debouncedSearch],
  );

  const {
    data: candidates,
    loading: candLoading,
    error: candError,
    reload: reloadCandidates,
  } = useFetch(
    (signal) =>
      apiList<CandidateListItem>(
        `/requisitions/${id}/candidates`,
        candQuery as never,
        signal,
      ),
    [id, JSON.stringify(candQuery)],
  );

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!req) return <EmptyState title="Requisition not found" />;

  async function startCall(candidateId: string) {
    try {
      await apiPost("/screening/start-call", {
        candidate_id: candidateId,
        requisition_id: id,
      });
      toast.success("Screening call started");
      reloadCandidates();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <div className="space-y-5">
      <Link
        href="/jobs"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft className="h-4 w-4" /> Back to jobs
      </Link>

      <Card>
        <CardBody className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold text-slate-800">
                {req.title}
              </h2>
              <StatusBadge status={req.status} />
              {req.seniority_level && (
                <Badge tone="purple">{titleCase(req.seniority_level)}</Badge>
              )}
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {[req.domain, req.department, req.location]
                .filter(Boolean)
                .join(" · ") || "—"}
            </p>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
              <span>
                Experience:{" "}
                {req.min_experience_years != null ||
                req.max_experience_years != null
                  ? `${req.min_experience_years ?? 0}–${
                      req.max_experience_years ?? "+"
                    } yrs`
                  : "—"}
              </span>
              <span>Openings: {formatNumber(req.number_of_openings)}</span>
              {req.work_mode && <span>Work mode: {titleCase(req.work_mode)}</span>}
              {(req.min_budget_ctc != null || req.max_budget_ctc != null) && (
                <span>
                  Budget: {formatCurrency(req.min_budget_ctc)} –{" "}
                  {formatCurrency(req.max_budget_ctc)}
                </span>
              )}
              <span>Created: {formatDate(req.created_at)}</span>
              {req.pipeline_count != null && (
                <span>Pipeline: {formatNumber(req.pipeline_count)}</span>
              )}
            </div>
          </div>
          {canEdit && (
            <Button variant="outline" onClick={() => setStatusOpen(true)}>
              <Pencil className="h-4 w-4" /> Update status
            </Button>
          )}
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Description + skills */}
        <Card className="lg:col-span-1">
          <CardHeader title="Details" />
          <CardBody className="space-y-4">
            {req.description && (
              <div>
                <p className="mb-1 text-xs font-semibold text-slate-500">
                  Description
                </p>
                <p className="whitespace-pre-wrap text-sm text-slate-600">
                  {req.description}
                </p>
              </div>
            )}
            <div>
              <p className="mb-2 text-xs font-semibold text-slate-500">
                Required skills
              </p>
              {req.skills.length === 0 ? (
                <p className="text-xs text-slate-400">No skills specified.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {req.skills.map((s, i) => (
                    <Badge
                      key={`${s.skill_id ?? s.skill_name}-${i}`}
                      tone={s.is_mandatory ? "indigo" : "gray"}
                    >
                      {s.skill_name}
                      {s.minimum_years != null && ` ${s.minimum_years}y+`}
                      {s.is_mandatory ? " *" : ""}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </CardBody>
        </Card>

        {/* Ranked candidates */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Ranked candidates"
            action={
              <Input
                placeholder="Search…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="h-9 w-44"
              />
            }
          />
          {candLoading ? (
            <LoadingState />
          ) : candError ? (
            <ErrorState message={candError} onRetry={reloadCandidates} />
          ) : !candidates || candidates.data.length === 0 ? (
            <EmptyState
              title="No matching candidates"
              description="No candidates ranked for this requisition yet."
            />
          ) : (
            <>
              <Table>
                <THead>
                  <TR>
                    <TH>Candidate</TH>
                    <TH>Experience</TH>
                    <TH className="w-40">Match</TH>
                    <TH>Actions</TH>
                  </TR>
                </THead>
                <TBody>
                  {candidates.data.map((c) => (
                    <TR key={c.id} className="hover:bg-slate-50">
                      <TD>
                        <Link
                          href={`/candidates/${c.id}`}
                          className="font-medium text-indigo-600 hover:underline"
                        >
                          {c.full_name}
                        </Link>
                        <p className="text-xs text-slate-400">
                          {c.current_company ?? c.email}
                        </p>
                      </TD>
                      <TD>
                        {c.total_experience_years != null
                          ? `${formatNumber(c.total_experience_years, 1)} yrs`
                          : "—"}
                      </TD>
                      <TD>
                        <ScoreBar value={c.match_score} />
                      </TD>
                      <TD>
                        {canManageCandidates && (
                          <div className="flex gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => startCall(c.id)}
                              title="Start screening"
                            >
                              <PhoneCall className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setScheduleFor(c.id)}
                              title="Schedule interview"
                            >
                              <CalendarPlus className="h-4 w-4" />
                            </Button>
                          </div>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pagination
                page={candidates.page}
                totalPages={candidates.total_pages}
                total={candidates.total}
                onPageChange={setPage}
              />
            </>
          )}
        </Card>
      </div>

      <UpdateStatusModal
        open={statusOpen}
        onClose={() => setStatusOpen(false)}
        requisitionId={req.id}
        current={req.status}
        onUpdated={reload}
      />

      {scheduleFor && (
        <ScheduleInterviewModal
          open={!!scheduleFor}
          onClose={() => setScheduleFor(null)}
          candidateId={scheduleFor}
          requisitionId={req.id}
          onScheduled={reloadCandidates}
        />
      )}
    </div>
  );
}

function UpdateStatusModal({
  open,
  onClose,
  requisitionId,
  current,
  onUpdated,
}: {
  open: boolean;
  onClose: () => void;
  requisitionId: string;
  current: string;
  onUpdated: () => void;
}) {
  const toast = useToast();
  const [status, setStatus] = useState(current);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await apiPatch(`/requisitions/${requisitionId}`, { status });
      toast.success("Status updated");
      onUpdated();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Update requisition status"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={save} loading={saving}>
            Save
          </Button>
        </>
      }
    >
      <Select
        label="Status"
        options={REQUISITION_STATUSES.map((s) => ({
          value: s,
          label: titleCase(s),
        }))}
        value={status}
        onChange={(e) => setStatus(e.target.value)}
      />
    </Modal>
  );
}
