"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ChevronDown,
  Clock,
  MapPin,
  Target,
  Users,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiList, apiPatch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useFetch } from "@/lib/hooks";
import type { CandidateListItem, ListResponse, RequisitionDetail } from "@/lib/types";
import { REQUISITION_STATUSES } from "@/lib/types";
import { formatCurrency, formatDate, titleCase } from "@/lib/utils";
import { PageHeader } from "@/components/common/page-header";
import { Stat } from "@/components/common/stat";
import { ScoreRing } from "@/components/common/score";
import { ScoreBadge, RequisitionStatusBadge } from "@/components/common/badges";
import { ErrorState, LoadingState, TableSkeleton } from "@/components/common/states";
import { AssignInterviewersPanel } from "@/components/jobs/assign-interviewers-panel";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { role } = useAuth();
  const canManage = role === "HR" || role === "DELIVERY_MANAGER" || role === "ADMIN";

  const { data: job, loading, error, reload } = useFetch<RequisitionDetail>(
    (signal) => apiGet<RequisitionDetail>(`/requisitions/${id}`, undefined, signal),
    [id],
  );

  const changeStatus = async (status: string) => {
    try {
      await apiPatch(`/requisitions/${id}`, { status });
      toast.success(`Marked ${titleCase(status)}`);
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  if (loading) return <LoadingState label="Loading job…" />;
  if (error || !job) return <ErrorState description={error ?? "Job not found"} onRetry={reload} />;

  return (
    <>
      <Button variant="ghost" size="sm" className="mb-3 -ml-2" onClick={() => router.back()}>
        <ArrowLeft className="size-4" /> Back to jobs
      </Button>

      <PageHeader
        eyebrow={job.domain ?? "Requisition"}
        title={job.title}
        action={
          <div className="flex items-center gap-2">
            <RequisitionStatusBadge status={job.status} />
            {canManage && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm">
                    Change status <ChevronDown className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {REQUISITION_STATUSES.map((s) => (
                    <DropdownMenuItem key={s} onClick={() => changeStatus(s)}>
                      {titleCase(s)}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
          <Card className="gap-5 p-5">
            <div className="grid grid-cols-2 gap-x-4 gap-y-4">
              <Stat label="Seniority" value={titleCase(job.seniority_level)} icon={<Target className="size-3.5" />} />
              <Stat label="Department" value={job.department ?? "—"} />
              <Stat label="Location" value={job.location ?? "—"} icon={<MapPin className="size-3.5" />} />
              <Stat label="Work mode" value={titleCase(job.work_mode)} />
              <Stat
                label="Experience"
                value={
                  job.min_experience_years != null || job.max_experience_years != null
                    ? `${job.min_experience_years ?? 0}–${job.max_experience_years ?? "∞"}y`
                    : "Any"
                }
                icon={<Clock className="size-3.5" />}
              />
              <Stat label="Openings" value={job.number_of_openings} icon={<Users className="size-3.5" />} />
              <Stat
                label="Budget"
                value={
                  job.min_budget_ctc || job.max_budget_ctc
                    ? `${formatCurrency(job.min_budget_ctc)} – ${formatCurrency(job.max_budget_ctc)}`
                    : "—"
                }
                icon={<Wallet className="size-3.5" />}
                className="col-span-2"
              />
              <Stat label="Created" value={formatDate(job.created_at)} />
              <Stat label="Pipeline" value={`${job.pipeline_count ?? 0} candidates`} />
            </div>
            <Separator />
            <div>
              <p className="text-muted-foreground mb-2 text-xs font-medium">Required skills</p>
              {job.skills?.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {job.skills.map((s) => (
                    <Badge key={s.skill_name} variant={s.is_mandatory ? "info" : "muted"}>
                      {s.skill_name}
                      {s.minimum_years ? ` · ${s.minimum_years}y` : ""}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">No skills specified.</p>
              )}
            </div>
          </Card>
        </div>

        <div className="lg:col-span-2">
          <Tabs defaultValue="pipeline">
            <TabsList>
              <TabsTrigger value="pipeline">Candidate Pipeline</TabsTrigger>
              <TabsTrigger value="description">Description</TabsTrigger>
              <TabsTrigger value="interviewers">Interviewers</TabsTrigger>
            </TabsList>

            <TabsContent value="pipeline" className="mt-4">
              <JobPipeline requisitionId={id} />
            </TabsContent>

            <TabsContent value="description" className="mt-4">
              <Card className="p-5">
                {job.description ? (
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{job.description}</p>
                ) : (
                  <p className="text-muted-foreground text-sm">No description provided.</p>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="interviewers" className="mt-4">
              <Card className="p-5">
                <AssignInterviewersPanel requisitionId={id} canManage={canManage} />
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </>
  );
}

function JobPipeline({ requisitionId }: { requisitionId: string }) {
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useFetch<ListResponse<CandidateListItem>>(
    (signal) =>
      apiList<CandidateListItem>(`/requisitions/${requisitionId}/candidates`, { page, limit: 15 }, signal),
    [requisitionId, page],
  );

  if (loading) return <Card className="p-5"><TableSkeleton rows={6} cols={3} /></Card>;
  if (error) return <ErrorState description={error} onRetry={reload} />;
  const rows = data?.data ?? [];
  if (!rows.length)
    return (
      <Card className="p-10 text-center">
        <p className="text-muted-foreground text-sm">No candidates scored for this role yet.</p>
      </Card>
    );

  return (
    <Card className="gap-0 divide-y p-0">
      {rows.map((c) => (
        <Link
          key={c.id}
          href={`/candidates/${c.id}`}
          className="hover:bg-muted/40 flex items-center gap-3 px-4 py-3 transition-colors"
        >
          <ScoreRing score={c.match_score} size={40} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{c.full_name}</p>
            <p className="text-muted-foreground truncate text-xs">
              {c.current_designation ?? "—"}
              {c.current_company ? ` · ${c.current_company}` : ""}
            </p>
          </div>
          <ScoreBadge score={c.match_score} />
        </Link>
      ))}
      {(data?.total_pages ?? 1) > 1 && (
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-muted-foreground text-xs">Page {page} of {data?.total_pages}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
            <Button variant="outline" size="sm" disabled={page >= (data?.total_pages ?? 1)} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
