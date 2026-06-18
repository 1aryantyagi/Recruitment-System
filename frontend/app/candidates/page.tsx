"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, Upload, Filter, X } from "lucide-react";
import { AppShell, PageHeader } from "@/components/AppShell";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { MultiSelect } from "@/components/ui/MultiSelect";
import { Badge } from "@/components/ui/Badge";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/Table";
import { Pagination } from "@/components/ui/Pagination";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/Spinner";
import { UploadResumesModal } from "@/components/candidates/UploadResumesModal";
import { useAuth } from "@/lib/auth";
import { apiList } from "@/lib/api";
import { useFetch, useDebounce } from "@/lib/hooks";
import { useSkills, useDomains } from "@/lib/meta";
import { formatNumber, titleCase } from "@/lib/utils";
import { WORK_MODES, type CandidateListItem } from "@/lib/types";

const SOURCES = ["REFERRAL", "JOB_BOARD", "LINKEDIN", "AGENCY", "DIRECT", "OTHER"];
const LIMIT = 20;

export default function CandidatesPage() {
  return (
    <AppShell>
      <CandidatesContent />
    </AppShell>
  );
}

function CandidatesContent() {
  const router = useRouter();
  const { canManageCandidates } = useAuth();
  const { skills } = useSkills();
  const { data: domains } = useDomains();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [minExp, setMinExp] = useState("");
  const [maxExp, setMaxExp] = useState("");
  const [workMode, setWorkMode] = useState("");
  const [source, setSource] = useState("");
  const [domainId, setDomainId] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);

  const debouncedSearch = useDebounce(search);

  const skillOptions = useMemo(
    () => skills.map((s) => ({ value: s.name, label: s.name })),
    [skills],
  );

  const query = useMemo(
    () => ({
      page,
      limit: LIMIT,
      search: debouncedSearch || undefined,
      skills: skillIds.length > 0 ? skillIds : undefined,
      min_exp: minExp || undefined,
      max_exp: maxExp || undefined,
      work_mode: workMode || undefined,
      source: source || undefined,
      domain_id: domainId || undefined,
    }),
    [page, debouncedSearch, skillIds, minExp, maxExp, workMode, source, domainId],
  );

  const { data, loading, error, reload } = useFetch(
    (signal) =>
      apiList<CandidateListItem>("/candidates", query as never, signal),
    [JSON.stringify(query)],
  );

  const hasFilters =
    !!debouncedSearch ||
    skillIds.length > 0 ||
    !!minExp ||
    !!maxExp ||
    !!workMode ||
    !!source ||
    !!domainId;

  function clearFilters() {
    setSearch("");
    setSkillIds([]);
    setMinExp("");
    setMaxExp("");
    setWorkMode("");
    setSource("");
    setDomainId("");
    setPage(1);
  }

  // Reset to page 1 when filters change.
  function onFilter<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPage(1);
    };
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Candidates"
        description="Search, filter and manage your talent pool"
        action={
          canManageCandidates ? (
            <Button onClick={() => setUploadOpen(true)}>
              <Upload className="h-4 w-4" /> Upload resumes
            </Button>
          ) : undefined
        }
      />

      {/* Filters */}
      <Card className="p-4">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
          <Filter className="h-4 w-4" /> Filters
          {hasFilters && (
            <button
              onClick={clearFilters}
              className="ml-auto flex items-center gap-1 text-xs text-indigo-600 hover:underline"
            >
              <X className="h-3 w-3" /> Clear
            </button>
          )}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <Input
              placeholder="Search name, email, company…"
              leftIcon={<Search className="h-4 w-4" />}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <MultiSelect
            options={skillOptions}
            selected={skillIds}
            onChange={onFilter(setSkillIds)}
            placeholder="Skills"
          />
          <Select
            options={WORK_MODES.map((w) => ({ value: w, label: titleCase(w) }))}
            value={workMode}
            onChange={(e) => onFilter(setWorkMode)(e.target.value)}
            placeholder="Any work mode"
          />
          <Input
            type="number"
            placeholder="Min exp (yrs)"
            value={minExp}
            onChange={(e) => onFilter(setMinExp)(e.target.value)}
          />
          <Input
            type="number"
            placeholder="Max exp (yrs)"
            value={maxExp}
            onChange={(e) => onFilter(setMaxExp)(e.target.value)}
          />
          <Select
            options={SOURCES.map((s) => ({ value: s, label: titleCase(s) }))}
            value={source}
            onChange={(e) => onFilter(setSource)(e.target.value)}
            placeholder="Any source"
          />
          <Select
            options={(domains ?? []).map((d) => ({
              value: d.id,
              label: d.name,
            }))}
            value={domainId}
            onChange={(e) => onFilter(setDomainId)(e.target.value)}
            placeholder="Any domain"
          />
        </div>
      </Card>

      {/* Table */}
      <Card>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : !data || data.data.length === 0 ? (
          <EmptyState
            title="No candidates found"
            description={
              hasFilters
                ? "Try adjusting your filters."
                : "Upload resumes to get started."
            }
          />
        ) : (
          <>
            <Table>
              <THead>
                <TR>
                  <TH>Name</TH>
                  <TH>Domain</TH>
                  <TH>Experience</TH>
                  <TH>Company</TH>
                  <TH>Location</TH>
                  <TH>Notice</TH>
                  <TH>Source</TH>
                </TR>
              </THead>
              <TBody>
                {data.data.map((c) => (
                  <TR
                    key={c.id}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() => router.push(`/candidates/${c.id}`)}
                  >
                    <TD>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-slate-800">
                          {c.full_name}
                        </span>
                        {c.is_blacklisted && (
                          <Badge tone="red">Blacklisted</Badge>
                        )}
                      </div>
                      <p className="text-xs text-slate-400">{c.email}</p>
                    </TD>
                    <TD>{c.domain ?? "—"}</TD>
                    <TD>
                      {c.total_experience_years != null
                        ? `${formatNumber(c.total_experience_years, 1)} yrs`
                        : "—"}
                    </TD>
                    <TD>
                      <div>{c.current_company ?? "—"}</div>
                      {c.current_designation && (
                        <p className="text-xs text-slate-400">
                          {c.current_designation}
                        </p>
                      )}
                    </TD>
                    <TD>{c.current_location ?? "—"}</TD>
                    <TD>
                      {c.notice_period_days != null
                        ? `${c.notice_period_days}d`
                        : "—"}
                    </TD>
                    <TD>
                      {c.source ? (
                        <Badge tone="blue">{titleCase(c.source)}</Badge>
                      ) : (
                        "—"
                      )}
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

      <UploadResumesModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={reload}
      />
    </div>
  );
}
