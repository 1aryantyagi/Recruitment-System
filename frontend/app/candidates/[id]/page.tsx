"use client";

import { use, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Mail,
  Phone,
  MapPin,
  Building2,
  Linkedin,
  Globe,
  FileText,
  ExternalLink,
  PhoneCall,
  CalendarPlus,
  Ban,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Tabs, type TabDef } from "@/components/ui/Tabs";
import { ScoreBar } from "@/components/ui/ScoreBar";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/Spinner";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { SkillsTab } from "@/components/candidates/SkillsTab";
import { BlacklistModal } from "@/components/candidates/BlacklistModal";
import { ScheduleInterviewModal } from "@/components/interviews/ScheduleInterviewModal";
import { useAuth } from "@/lib/auth";
import { apiGet, apiPost } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatNumber,
  titleCase,
} from "@/lib/utils";
import type { CandidateDetail } from "@/lib/types";

export default function CandidateDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <AppShell>
      <CandidateContent id={id} />
    </AppShell>
  );
}

function CandidateContent({ id }: { id: string }) {
  const { canManageCandidates, isAdmin } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState("overview");
  const [blacklistOpen, setBlacklistOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [acting, setActing] = useState(false);

  const { data: c, loading, error, reload } = useFetch<CandidateDetail>(
    () => apiGet<CandidateDetail>(`/candidates/${id}`),
    [id],
  );

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!c) return <EmptyState title="Candidate not found" />;

  async function startCall() {
    if (!c) return;
    setActing(true);
    try {
      await apiPost("/screening/start-call", { candidate_id: c.id });
      toast.success("Screening call started");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setActing(false);
    }
  }

  async function openResume() {
    if (!c) return;
    try {
      const res = await apiGet<{ url: string }>(`/candidates/${c.id}/resume`);
      if (res?.url) window.open(res.url, "_blank");
      else toast.error("No resume file available");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  const tabs: TabDef[] = [
    { key: "overview", label: "Overview" },
    { key: "skills", label: "Skills", count: c.skills.length },
    { key: "resumes", label: "Resumes", count: c.resumes.length },
    { key: "scores", label: "Scores", count: c.scores.length },
    { key: "screening", label: "Screening", count: c.calls.length },
    { key: "interviews", label: "Interviews", count: c.interviews.length },
  ];

  return (
    <div className="space-y-5">
      <Link
        href="/candidates"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft className="h-4 w-4" /> Back to candidates
      </Link>

      {/* Header */}
      <Card>
        <CardBody className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-indigo-100 text-lg font-semibold text-indigo-700">
              {c.full_name
                .split(" ")
                .slice(0, 2)
                .map((p) => p[0])
                .join("")}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold text-slate-800">
                  {c.full_name}
                </h2>
                {c.is_blacklisted && <Badge tone="red">Blacklisted</Badge>}
                {c.domain && <Badge tone="purple">{c.domain}</Badge>}
              </div>
              <p className="text-sm text-slate-500">
                {[c.current_designation, c.current_company]
                  .filter(Boolean)
                  .join(" @ ") || "—"}
              </p>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                <span className="flex items-center gap-1">
                  <Mail className="h-3.5 w-3.5" /> {c.email}
                </span>
                {c.current_location && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3.5 w-3.5" /> {c.current_location}
                  </span>
                )}
                {c.total_experience_years != null && (
                  <span>
                    {formatNumber(c.total_experience_years, 1)} yrs exp
                  </span>
                )}
              </div>
            </div>
          </div>

          {canManageCandidates && (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={openResume}>
                <FileText className="h-4 w-4" /> Resume
              </Button>
              <Button
                variant="outline"
                onClick={startCall}
                loading={acting}
              >
                <PhoneCall className="h-4 w-4" /> Start screening
              </Button>
              <Button onClick={() => setScheduleOpen(true)}>
                <CalendarPlus className="h-4 w-4" /> Schedule
              </Button>
              {!c.is_blacklisted ? (
                <Button
                  variant="danger"
                  onClick={() => setBlacklistOpen(true)}
                >
                  <Ban className="h-4 w-4" /> Blacklist
                </Button>
              ) : isAdmin ? (
                <RemoveBlacklistButton candidateId={c.id} onDone={reload} />
              ) : null}
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <Tabs tabs={tabs} active={tab} onChange={setTab} className="px-3" />
        <CardBody>
          {tab === "overview" && <OverviewTab c={c} />}
          {tab === "skills" && (
            <SkillsTab
              candidate={c}
              canEdit={canManageCandidates}
              onChanged={reload}
            />
          )}
          {tab === "resumes" && (
            <ResumesTab c={c} canEdit={canManageCandidates} onChanged={reload} />
          )}
          {tab === "scores" && <ScoresTab c={c} />}
          {tab === "screening" && (
            <ScreeningTab
              c={c}
              canEdit={canManageCandidates}
              onStartCall={startCall}
              acting={acting}
            />
          )}
          {tab === "interviews" && (
            <InterviewsTab c={c} onSchedule={() => setScheduleOpen(true)} />
          )}
        </CardBody>
      </Card>

      <BlacklistModal
        open={blacklistOpen}
        onClose={() => setBlacklistOpen(false)}
        candidateId={c.id}
        onDone={reload}
      />
      <ScheduleInterviewModal
        open={scheduleOpen}
        onClose={() => setScheduleOpen(false)}
        candidateId={c.id}
        onScheduled={reload}
      />
    </div>
  );
}

function RemoveBlacklistButton({
  candidateId,
  onDone,
}: {
  candidateId: string;
  onDone: () => void;
}) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  async function remove() {
    setLoading(true);
    try {
      const { apiDelete } = await import("@/lib/api");
      await apiDelete(`/candidates/${candidateId}/blacklist`);
      toast.success("Removed from blacklist");
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <Button variant="outline" onClick={remove} loading={loading}>
      Un-blacklist
    </Button>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value?: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-sm text-slate-700">{value ?? "—"}</p>
    </div>
  );
}

function OverviewTab({ c }: { c: CandidateDetail }) {
  return (
    <div className="space-y-6">
      {c.ai_summary && (
        <div className="rounded-lg bg-indigo-50/60 p-4">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-indigo-500">
            AI Summary
          </p>
          <p className="text-sm text-slate-700">{c.ai_summary}</p>
        </div>
      )}

      <div>
        <h4 className="mb-3 text-sm font-semibold text-slate-700">Contact</h4>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field label="Email" value={c.email} />
          <Field
            label="Phone"
            value={
              c.phone ? (
                <span className="flex items-center gap-1">
                  <Phone className="h-3.5 w-3.5 text-slate-400" /> {c.phone}
                </span>
              ) : undefined
            }
          />
          <Field label="Location" value={c.current_location} />
          <Field
            label="LinkedIn"
            value={
              c.linkedin_url ? (
                <a
                  href={c.linkedin_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-indigo-600 hover:underline"
                >
                  <Linkedin className="h-3.5 w-3.5" /> Profile
                </a>
              ) : undefined
            }
          />
          <Field
            label="Portfolio"
            value={
              c.portfolio_url ? (
                <a
                  href={c.portfolio_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-indigo-600 hover:underline"
                >
                  <Globe className="h-3.5 w-3.5" /> Link
                </a>
              ) : undefined
            }
          />
        </div>
      </div>

      <div>
        <h4 className="mb-3 text-sm font-semibold text-slate-700">
          Experience & Compensation
        </h4>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field
            label="Current company"
            value={
              c.current_company ? (
                <span className="flex items-center gap-1">
                  <Building2 className="h-3.5 w-3.5 text-slate-400" />
                  {c.current_company}
                </span>
              ) : undefined
            }
          />
          <Field label="Designation" value={c.current_designation} />
          <Field
            label="Total experience"
            value={
              c.total_experience_years != null
                ? `${formatNumber(c.total_experience_years, 1)} yrs`
                : undefined
            }
          />
          <Field label="Current CTC" value={formatCurrency(c.current_ctc)} />
          <Field label="Expected CTC" value={formatCurrency(c.expected_ctc)} />
          <Field
            label="Notice period"
            value={
              c.notice_period_days != null
                ? `${c.notice_period_days} days`
                : undefined
            }
          />
          <Field
            label="Work mode"
            value={
              c.work_mode_preference
                ? titleCase(c.work_mode_preference)
                : undefined
            }
          />
          <Field
            label="Shift preference"
            value={c.shift_preference ? titleCase(c.shift_preference) : undefined}
          />
          <Field
            label="Availability"
            value={formatDate(c.availability_date)}
          />
          <Field
            label="Source"
            value={c.source ? titleCase(c.source) : undefined}
          />
          <Field label="Source detail" value={c.source_detail} />
        </div>
      </div>

      {c.blacklist_note && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3">
          <p className="text-xs font-semibold text-red-600">Blacklist note</p>
          <p className="text-sm text-red-700">{c.blacklist_note}</p>
        </div>
      )}
    </div>
  );
}

function ResumesTab({
  c,
  canEdit,
  onChanged,
}: {
  c: CandidateDetail;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [uploading, setUploading] = useState(false);

  async function open(resumeHasFile: boolean) {
    if (!resumeHasFile) {
      toast.error("This version has no stored file");
      return;
    }
    try {
      const res = await apiGet<{ url: string }>(`/candidates/${c.id}/resume`);
      if (res?.url) window.open(res.url, "_blank");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function uploadNew(file: File) {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { apiUpload } = await import("@/lib/api");
      await apiUpload(`/candidates/${c.id}/resume`, fd);
      toast.success("New resume version uploaded");
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-4">
      {c.resumes.length === 0 ? (
        <EmptyState title="No resumes on file" />
      ) : (
        <div className="space-y-2">
          {c.resumes.map((r) => (
            <div
              key={r.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2.5"
            >
              <div className="flex items-center gap-3">
                <FileText className="h-5 w-5 text-slate-400" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-700">
                      Resume
                    </span>
                    {r.is_latest && <Badge tone="green">Latest</Badge>}
                  </div>
                  <p className="text-xs text-slate-400">
                    Uploaded {formatDateTime(r.uploaded_at)}
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => open(r.has_file)}
                disabled={!r.has_file}
              >
                <ExternalLink className="h-4 w-4" /> Open
              </Button>
            </div>
          ))}
        </div>
      )}

      {canEdit && (
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
          {uploading ? "Uploading…" : "Upload new version"}
          <input
            type="file"
            accept=".pdf,.doc,.docx"
            className="hidden"
            disabled={uploading}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadNew(f);
            }}
          />
        </label>
      )}
    </div>
  );
}

function ScoresTab({ c }: { c: CandidateDetail }) {
  if (c.scores.length === 0)
    return <EmptyState title="No requisition scores yet" />;
  return (
    <Table>
      <THead>
        <TR>
          <TH>Requisition</TH>
          <TH>Total</TH>
          <TH>Skills</TH>
          <TH>Experience</TH>
          <TH>Depth</TH>
          <TH>Location</TH>
          <TH>Notice</TH>
        </TR>
      </THead>
      <TBody>
        {c.scores.map((s) => (
          <TR key={s.requisition_id} className="hover:bg-slate-50">
            <TD>
              <Link
                href={`/jobs/${s.requisition_id}`}
                className="text-indigo-600 hover:underline"
              >
                {s.requisition_id.slice(0, 8)}…
              </Link>
            </TD>
            <TD className="w-32">
              <ScoreBar value={s.total_score} />
            </TD>
            <TD>{formatNumber(s.skills_score, 1)}</TD>
            <TD>{formatNumber(s.experience_score, 1)}</TD>
            <TD>{formatNumber(s.skills_depth_score, 1)}</TD>
            <TD>{formatNumber(s.location_score, 1)}</TD>
            <TD>{formatNumber(s.notice_period_score, 1)}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

function ScreeningTab({
  c,
  canEdit,
  onStartCall,
  acting,
}: {
  c: CandidateDetail;
  canEdit: boolean;
  onStartCall: () => void;
  acting: boolean;
}) {
  return (
    <div className="space-y-4">
      {canEdit && (
        <Button onClick={onStartCall} loading={acting}>
          <PhoneCall className="h-4 w-4" /> Start screening call
        </Button>
      )}
      {c.calls.length === 0 ? (
        <EmptyState title="No screening calls yet" />
      ) : (
        <div className="space-y-3">
          {c.calls.map((call) => (
            <Card key={call.id}>
              <CardHeader
                title={
                  <span className="flex items-center gap-2">
                    <StatusBadge status={call.status} />
                    {call.ai_score != null && (
                      <span className="text-xs text-slate-500">
                        AI score: {formatNumber(call.ai_score, 1)}
                      </span>
                    )}
                  </span>
                }
                description={formatDateTime(call.called_at)}
              />
              <CardBody className="space-y-3">
                {call.transcript && (
                  <div>
                    <p className="mb-1 text-xs font-semibold text-slate-500">
                      Transcript
                    </p>
                    <p className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-xs text-slate-600">
                      {call.transcript}
                    </p>
                  </div>
                )}
                {call.screening_answers &&
                  Object.keys(call.screening_answers).length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-semibold text-slate-500">
                        Q&A
                      </p>
                      <dl className="space-y-1">
                        {Object.entries(call.screening_answers).map(
                          ([q, a]) => (
                            <div
                              key={q}
                              className="rounded-md bg-slate-50 p-2 text-xs"
                            >
                              <dt className="font-medium text-slate-600">
                                {q}
                              </dt>
                              <dd className="text-slate-500">{String(a)}</dd>
                            </div>
                          ),
                        )}
                      </dl>
                    </div>
                  )}
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function InterviewsTab({
  c,
  onSchedule,
}: {
  c: CandidateDetail;
  onSchedule: () => void;
}) {
  const { canManageCandidates } = useAuth();
  return (
    <div className="space-y-4">
      {canManageCandidates && (
        <Button onClick={onSchedule}>
          <CalendarPlus className="h-4 w-4" /> Schedule interview
        </Button>
      )}
      {c.interviews.length === 0 ? (
        <EmptyState title="No interviews scheduled" />
      ) : (
        <div className="space-y-3">
          {c.interviews.map((iv) => (
            <Card key={iv.id}>
              <CardHeader
                title={
                  <span className="flex items-center gap-2">
                    <Badge tone="indigo">{iv.round_type}</Badge>
                    {iv.round_number != null && (
                      <span className="text-xs text-slate-400">
                        Round {iv.round_number}
                      </span>
                    )}
                    <StatusBadge status={iv.status} />
                  </span>
                }
                description={formatDateTime(iv.scheduled_at)}
                action={
                  iv.meeting_link ? (
                    <a
                      href={iv.meeting_link}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-indigo-600 hover:underline"
                    >
                      Join link
                    </a>
                  ) : undefined
                }
              />
              {(iv.ai_overall_rating != null ||
                iv.ai_analysis != null ||
                iv.feedback != null) && (
                <CardBody className="space-y-2 text-xs">
                  {iv.ai_overall_rating != null && (
                    <p className="text-slate-600">
                      <span className="font-medium">AI rating:</span>{" "}
                      {formatNumber(iv.ai_overall_rating, 1)}
                    </p>
                  )}
                  {iv.ai_analysis != null && (
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-2 text-slate-600">
                      {typeof iv.ai_analysis === "string"
                        ? iv.ai_analysis
                        : JSON.stringify(iv.ai_analysis, null, 2)}
                    </pre>
                  )}
                </CardBody>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
