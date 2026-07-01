"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  Briefcase,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  ChevronDown,
  Clock,
  FileText,
  Linkedin,
  Mail,
  MapPin,
  Phone,
  PhoneCall,
  Sparkles,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useFetch } from "@/lib/hooks";
import type { CandidateApplication, CandidateCall, CandidateDetail } from "@/lib/types";
import {
  cn,
  formatCurrency,
  formatDate,
  formatDateTime,
  scoreToPercent,
  titleCase,
} from "@/lib/utils";
import { Stat } from "@/components/common/stat";
import { ScoreRing, ScoreBar } from "@/components/common/score";
import { InterviewStatusBadge, StageBadge } from "@/components/common/badges";
import { InitialsAvatar } from "@/components/common/avatar-name";
import { ErrorState, LoadingState } from "@/components/common/states";
import { BlacklistModal } from "@/components/candidates/blacklist-modal";
import { RolePipeline } from "@/components/candidates/role-pipeline";
import { VoiceScreeningModal } from "@/components/candidates/voice-screening-modal";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function CandidateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { canManageCandidates, isHR } = useAuth();
  const [blacklistOpen, setBlacklistOpen] = useState(false);
  const [screenOpen, setScreenOpen] = useState(false);

  const { data: c, loading, error, reload } = useFetch<CandidateDetail>(
    (signal) => apiGet<CandidateDetail>(`/candidates/${id}`, undefined, signal),
    [id],
  );

  const openResume = async () => {
    try {
      const res = await apiGet<{ url: string }>(`/candidates/${id}/resume`);
      window.open(res.url, "_blank");
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  if (loading) return <LoadingState label="Loading candidate…" />;
  if (error || !c)
    return <ErrorState description={error ?? "Candidate not found"} onRetry={reload} />;

  const bestScore = [...(c.scores ?? [])].sort(
    (a, b) => (b.total_score ?? 0) - (a.total_score ?? 0),
  )[0];

  // The single role this candidate is primarily judged on: the highest-match
  // application (match_score, falling back to the resume/ATS score), preferring
  // active applications over closed ones. The hiring-stages pipeline — resume +
  // telephonic scores — is shown for this one role only, so judgment focuses on
  // the top role the candidate is appearing for rather than spanning every role.
  const appScore = (a: CandidateApplication) =>
    a.match_score ??
    c.scores?.find((s) => s.requisition_id === a.requisition_id)?.total_score ??
    0;
  const isClosed = (a: CandidateApplication) =>
    a.status === "REJECTED" || a.status === "WITHDRAWN";
  const primaryApp = [...(c.applications ?? [])].sort((a, b) => {
    if (isClosed(a) !== isClosed(b)) return isClosed(a) ? 1 : -1; // active first
    return appScore(b) - appScore(a); // then highest match
  })[0];
  const otherApps = (c.applications ?? []).filter((a) => a.id !== primaryApp?.id);

  return (
    <>
      <Button variant="ghost" size="sm" className="mb-3 -ml-2" onClick={() => router.back()}>
        <ArrowLeft className="size-4" /> Back
      </Button>

      {/* Header */}
      <Card className="mb-6 gap-0 p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <InitialsAvatar name={c.full_name} size="lg" />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight">{c.full_name}</h1>
                {c.is_blacklisted && <Badge variant="destructive">Blacklisted</Badge>}
              </div>
              <p className="text-muted-foreground mt-0.5 text-sm">
                {c.current_designation ?? "—"}
                {c.current_company ? ` · ${c.current_company}` : ""}
              </p>
              <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                <span className="inline-flex items-center gap-1"><Mail className="size-3.5" /> {c.email}</span>
                {c.phone && <span className="inline-flex items-center gap-1"><Phone className="size-3.5" /> {c.phone}</span>}
                {c.current_location && <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" /> {c.current_location}</span>}
                {c.linkedin_url && (
                  <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="hover:text-foreground inline-flex items-center gap-1">
                    <Linkedin className="size-3.5" /> LinkedIn
                  </a>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={openResume}>
              <FileText className="size-4" /> Resume
            </Button>
            {isHR && (
              <Button variant="outline" size="sm" onClick={() => setScreenOpen(true)}>
                <PhoneCall className="size-4" /> Screen
              </Button>
            )}
            <Button size="sm" onClick={() => router.push(`/interviews?candidate=${id}`)}>
              <CalendarPlus className="size-4" /> Schedule
            </Button>
            {canManageCandidates && !c.is_blacklisted && (
              <Button variant="ghost" size="icon-sm" className="text-destructive" onClick={() => setBlacklistOpen(true)} aria-label="Blacklist">
                <Ban className="size-4" />
              </Button>
            )}
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left column */}
        <div className="space-y-6 lg:col-span-1">
          {/* AI analysis */}
          <Card className="gap-4 p-5">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="text-primary size-4" /> AI Analysis
              </h2>
              {bestScore && <ScoreRing score={bestScore.total_score} size={48} />}
            </div>
            {c.ai_summary ? (
              <p className="text-muted-foreground text-sm leading-relaxed">{c.ai_summary}</p>
            ) : (
              <p className="text-muted-foreground text-sm italic">No AI summary generated yet.</p>
            )}
            {bestScore && (
              <div className="space-y-2.5">
                <p className="text-muted-foreground text-xs font-medium">
                  Match breakdown · {bestScore.requisition_title ?? "Top requisition"}
                </p>
                <ScoreBar label="Skills" score={bestScore.skills_score} />
                <ScoreBar label="Experience" score={bestScore.experience_score} />
                <ScoreBar label="Skill depth" score={bestScore.skills_depth_score} />
                <ScoreBar label="Location" score={bestScore.location_score} />
                <ScoreBar label="Notice period" score={bestScore.notice_period_score} />
              </div>
            )}
            <Separator />
            <div>
              <p className="text-muted-foreground mb-1.5 text-xs font-medium">Risk assessment</p>
              <RiskRow label="Notice period" ok={(c.notice_period_days ?? 99) <= 60} value={c.notice_period_days != null ? `${c.notice_period_days} days` : "Unknown"} />
              <RiskRow label="Availability" ok={!!c.availability_date} value={c.availability_date ? formatDate(c.availability_date) : "Not provided"} />
              <RiskRow label="Compensation fit" ok={!!c.expected_ctc} value={c.expected_ctc ? formatCurrency(c.expected_ctc) : "Unknown"} />
            </div>
          </Card>

          {/* Timeline */}
          <Card className="gap-4 p-5">
            <h2 className="text-sm font-semibold">Activity Timeline</h2>
            <Timeline candidate={c} />
          </Card>
        </div>

        {/* Right column — tabs */}
        <div className="lg:col-span-2">
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="skills">Skills ({c.skills?.length ?? 0})</TabsTrigger>
              <TabsTrigger value="applications">Applications ({c.applications?.length ?? 0})</TabsTrigger>
              <TabsTrigger value="interviews">Interviews ({c.interviews?.length ?? 0})</TabsTrigger>
              <TabsTrigger value="calls">Calls ({c.calls?.length ?? 0})</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="mt-4">
              <Card className="p-5">
                <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3">
                  <Stat label="Experience" value={c.total_experience_years != null ? `${c.total_experience_years} years` : "—"} icon={<Briefcase className="size-3.5" />} />
                  <Stat label="Domain" value={c.domain ?? "—"} />
                  <Stat label="Work mode" value={titleCase(c.work_mode_preference)} icon={<MapPin className="size-3.5" />} />
                  <Stat label="Current CTC" value={c.current_ctc ? formatCurrency(c.current_ctc) : "—"} icon={<Wallet className="size-3.5" />} />
                  <Stat label="Expected CTC" value={c.expected_ctc ? formatCurrency(c.expected_ctc) : "—"} icon={<Wallet className="size-3.5" />} />
                  <Stat label="Notice period" value={c.notice_period_days != null ? `${c.notice_period_days} days` : "—"} icon={<Clock className="size-3.5" />} />
                  <Stat label="Shift" value={titleCase(c.shift_preference)} />
                  <Stat label="Source" value={titleCase(c.source)} />
                  <Stat label="Added" value={formatDate(c.created_at)} />
                </div>
                {c.is_blacklisted && c.blacklist_note && (
                  <div className="bg-destructive/5 text-destructive mt-5 rounded-lg border p-3 text-sm">
                    <strong>Blacklisted:</strong> {c.blacklist_note}
                  </div>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="skills" className="mt-4">
              <Card className="p-5">
                {c.skills?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {c.skills.map((s) => (
                      <div key={s.id} className="bg-muted/50 flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm">
                        {s.is_verified && <CheckCircle2 className="size-3.5 text-emerald-500" />}
                        <span className="font-medium">{s.skill_name}</span>
                        {s.proficiency_level && (
                          <Badge variant="muted" className="text-[10px]">{titleCase(s.proficiency_level)}</Badge>
                        )}
                        {s.years_of_experience != null && (
                          <span className="text-muted-foreground text-xs">{s.years_of_experience}y</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyTab text="No skills extracted." />
                )}
              </Card>
            </TabsContent>

            <TabsContent value="applications" className="mt-4 space-y-3">
              {primaryApp ? (
                <>
                  <ApplicationPipelineCard c={c} a={primaryApp} />
                  {otherApps.length > 0 && (
                    <p className="text-muted-foreground px-1 text-xs">
                      Also applied to{" "}
                      {otherApps.map((a, i) => {
                        const t =
                          c.scores?.find((s) => s.requisition_id === a.requisition_id)
                            ?.requisition_title ?? `${a.requisition_id.slice(0, 8)}…`;
                        return (
                          <span key={a.id}>
                            {i > 0 && ", "}
                            <Link href={`/jobs/${a.requisition_id}`} className="hover:underline">
                              {t}
                            </Link>
                          </span>
                        );
                      })}
                      . Judged on the top-matched role above.
                    </p>
                  )}
                </>
              ) : (
                <Card className="p-5"><EmptyTab text="Not applied to any requisitions." /></Card>
              )}
            </TabsContent>

            <TabsContent value="interviews" className="mt-4 space-y-2">
              {c.interviews?.length ? (
                c.interviews.map((iv) => (
                  <Card key={iv.id} className="gap-2 p-4">
                    <div className="flex items-center gap-3">
                      <CalendarClock className="text-muted-foreground size-4" />
                      <span className="text-sm font-medium">
                        {iv.round_type} {iv.round_number ? `· Round ${iv.round_number}` : ""}
                      </span>
                      <InterviewStatusBadge status={iv.status} className="ml-auto" />
                    </div>
                    <div className="text-muted-foreground flex flex-wrap items-center gap-3 pl-7 text-xs">
                      {iv.scheduled_at && <span>{formatDateTime(iv.scheduled_at)}</span>}
                      {iv.ai_overall_rating != null && (
                        <span className="inline-flex items-center gap-1">
                          <Sparkles className="size-3" /> AI {scoreToPercent(iv.ai_overall_rating)}
                        </span>
                      )}
                      {(iv.status === "SCHEDULED" || iv.status === "RESCHEDULED") &&
                        iv.invite_sent === false && (
                          <span className="text-destructive inline-flex items-center gap-1 font-medium">
                            <AlertTriangle className="size-3" /> Invite not sent
                          </span>
                        )}
                    </div>
                  </Card>
                ))
              ) : (
                <Card className="p-5"><EmptyTab text="No interviews scheduled." /></Card>
              )}
            </TabsContent>

            <TabsContent value="calls" className="mt-4 space-y-2">
              {c.calls?.length ? (
                c.calls.map((call) => <CallCard key={call.id} call={call} />)
              ) : (
                <Card className="p-5"><EmptyTab text="No screening calls yet." /></Card>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <BlacklistModal
        open={blacklistOpen}
        onOpenChange={setBlacklistOpen}
        candidateId={c.id}
        candidateName={c.full_name}
        onDone={reload}
      />

      <VoiceScreeningModal
        open={screenOpen}
        onOpenChange={setScreenOpen}
        candidateId={c.id}
        applications={c.applications ?? []}
        scores={c.scores ?? []}
        onStarted={reload}
      />
    </>
  );
}

function RiskRow({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className="flex items-center justify-between py-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("inline-flex items-center gap-1 font-medium", ok ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400")}>
        <span className={cn("size-1.5 rounded-full", ok ? "bg-emerald-500" : "bg-amber-500")} />
        {value}
      </span>
    </div>
  );
}

function EmptyTab({ text }: { text: string }) {
  return <p className="text-muted-foreground py-8 text-center text-sm">{text}</p>;
}

function ApplicationPipelineCard({ c, a }: { c: CandidateDetail; a: CandidateApplication }) {
  const title = c.scores?.find((s) => s.requisition_id === a.requisition_id)?.requisition_title;
  return (
    <Card className="gap-3 p-4">
      <div className="flex items-center gap-3">
        <Briefcase className="text-muted-foreground size-4 shrink-0" />
        <Link href={`/jobs/${a.requisition_id}`} className="flex-1 truncate text-sm font-medium hover:underline">
          {title ?? `${a.requisition_id.slice(0, 8)}…`}
        </Link>
        {a.match_score != null && (
          <span className="text-muted-foreground text-xs tabular-nums">{scoreToPercent(a.match_score)} match</span>
        )}
        <StageBadge status={a.status} />
      </div>
      <Separator />
      <p className="text-muted-foreground text-xs font-medium">Hiring stages</p>
      <RolePipeline c={c} requisitionId={a.requisition_id} />
    </Card>
  );
}

function CallCard({ call }: { call: CandidateCall }) {
  const [open, setOpen] = useState(false);
  // Only offer a toggle when the transcript is long enough to be clipped.
  const isLong = (call.transcript?.length ?? 0) > 160;

  return (
    <Card className="gap-2 p-4">
      <div className="flex items-center gap-3">
        <PhoneCall className="text-muted-foreground size-4" />
        <span className="text-sm font-medium">{titleCase(call.status)}</span>
        {call.ai_score != null && (
          <Badge variant="info" className="ml-auto">AI {scoreToPercent(call.ai_score)}</Badge>
        )}
      </div>
      {call.transcript && (
        <div className="pl-7">
          <p
            className={cn(
              "text-muted-foreground text-xs leading-relaxed",
              open ? "whitespace-pre-wrap" : "line-clamp-2",
            )}
          >
            {call.transcript}
          </p>
          {isLong && (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="text-primary mt-1.5 inline-flex items-center gap-1 text-xs font-medium hover:underline"
            >
              {open ? "Show less" : "Show full transcript"}
              <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
            </button>
          )}
        </div>
      )}
      {call.called_at && (
        <p className="text-muted-foreground pl-7 text-xs">{formatDateTime(call.called_at)}</p>
      )}
    </Card>
  );
}

function Timeline({ candidate }: { candidate: CandidateDetail }) {
  const events: { label: string; date?: string | null; icon: typeof Clock }[] = [
    { label: "Applied", date: candidate.created_at, icon: FileText },
    ...(candidate.calls ?? []).map((c) => ({
      label: `Screening call · ${titleCase(c.status)}`,
      date: c.called_at,
      icon: PhoneCall,
    })),
    ...(candidate.interviews ?? []).map((i) => ({
      label: `${i.round_type} interview · ${titleCase(i.status)}`,
      date: i.scheduled_at,
      icon: CalendarClock,
    })),
  ]
    .filter((e) => e.date)
    .sort((a, b) => new Date(a.date!).getTime() - new Date(b.date!).getTime());

  if (!events.length)
    return <p className="text-muted-foreground text-sm">No activity recorded yet.</p>;

  return (
    <div className="relative space-y-4 pl-1">
      {events.map((e, i) => (
        <div key={i} className="relative flex gap-3">
          <div className="flex flex-col items-center">
            <span className="bg-primary/10 text-primary flex size-7 items-center justify-center rounded-full">
              <e.icon className="size-3.5" />
            </span>
            {i < events.length - 1 && <span className="bg-border mt-1 w-px flex-1" />}
          </div>
          <div className="-mt-0.5 pb-1">
            <p className="text-sm font-medium">{e.label}</p>
            <p className="text-muted-foreground text-xs">{formatDateTime(e.date)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
