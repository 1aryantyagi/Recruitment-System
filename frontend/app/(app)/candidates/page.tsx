"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Download,
  Search,
  SlidersHorizontal,
  Upload,
  Users,
} from "lucide-react";

import { apiList } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDebounce, useFetch } from "@/lib/hooks";
import { useDomains } from "@/lib/meta";
import type { CandidateListItem, ListResponse } from "@/lib/types";
import { WORK_MODES } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";
import { PageHeader } from "@/components/common/page-header";
import { FilterBar } from "@/components/common/filter-bar";
import { DataTable, type Column } from "@/components/common/data-table";
import { EmptyState } from "@/components/common/states";
import { AvatarName } from "@/components/common/avatar-name";
import { UploadResumesModal } from "@/components/candidates/upload-resumes-modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Label } from "@/components/ui/label";

const SOURCES = ["LINKEDIN", "NAUKRI", "EMAIL", "REFERRAL", "GMAIL", "OTHER"];
const ALL = "__all__";
const LIMIT = 20;

export default function CandidatesPage() {
  const router = useRouter();
  const { canManageCandidates } = useAuth();
  const { data: domains } = useDomains();

  const [search, setSearch] = useState("");
  const [domainId, setDomainId] = useState(ALL);
  const [workMode, setWorkMode] = useState(ALL);
  const [source, setSource] = useState(ALL);
  const [minExp, setMinExp] = useState("");
  const [maxExp, setMaxExp] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [uploadOpen, setUploadOpen] = useState(false);

  const debSearch = useDebounce(search, 350);

  const query = useMemo(
    () => ({
      page,
      limit: LIMIT,
      search: debSearch || undefined,
      domain_id: domainId === ALL ? undefined : domainId,
      work_mode: workMode === ALL ? undefined : workMode,
      source: source === ALL ? undefined : source,
      min_exp: minExp || undefined,
      max_exp: maxExp || undefined,
    }),
    [page, debSearch, domainId, workMode, source, minExp, maxExp],
  );

  const { data, loading, error, reload } = useFetch<ListResponse<CandidateListItem>>(
    (signal) => apiList<CandidateListItem>("/candidates", query, signal),
    [JSON.stringify(query)],
  );

  const rows = data?.data ?? [];
  const totalPages = data?.total_pages ?? 1;

  const toggleAll = () => {
    setSelected((prev) =>
      prev.size === rows.length ? new Set() : new Set(rows.map((r) => r.id)),
    );
  };
  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const exportCsv = () => {
    const picked = selected.size ? rows.filter((r) => selected.has(r.id)) : rows;
    const header = ["Name", "Email", "Domain", "Experience", "Company", "Location", "Source"];
    const lines = picked.map((c) =>
      [c.full_name, c.email, c.domain ?? "", c.total_experience_years ?? "", c.current_company ?? "", c.current_location ?? "", c.source ?? ""]
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "candidates.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const resetPageThen = (fn: () => void) => {
    fn();
    setPage(1);
  };

  const columns: Column<CandidateListItem>[] = [
    {
      key: "select",
      header: (
        <Checkbox
          checked={rows.length > 0 && selected.size === rows.length}
          onCheckedChange={toggleAll}
          aria-label="Select all"
        />
      ),
      headClassName: "w-10",
      cell: (c) => (
        <span onClick={(e) => e.stopPropagation()}>
          <Checkbox
            checked={selected.has(c.id)}
            onCheckedChange={() => toggleOne(c.id)}
            aria-label="Select row"
          />
        </span>
      ),
    },
    {
      key: "candidate",
      header: "Candidate",
      cell: (c) => <AvatarName name={c.full_name} subtitle={c.email} />,
    },
    {
      key: "role",
      header: "Current role",
      cell: (c) => (
        <div className="text-sm">
          <p className="font-medium">{c.current_designation ?? "—"}</p>
          <p className="text-muted-foreground text-xs">{c.current_company ?? "—"}</p>
        </div>
      ),
    },
    {
      key: "domain",
      header: "Domain",
      cell: (c) =>
        c.domain ? <Badge variant="secondary">{c.domain}</Badge> : <span className="text-muted-foreground">—</span>,
    },
    {
      key: "exp",
      header: "Exp",
      align: "right",
      cell: (c) =>
        c.total_experience_years != null ? (
          <span className="tabular-nums">{c.total_experience_years}y</span>
        ) : (
          "—"
        ),
    },
    {
      key: "location",
      header: "Location",
      cell: (c) => c.current_location ?? "—",
    },
    {
      key: "source",
      header: "Source",
      cell: (c) => (c.source ? <Badge variant="muted">{titleCase(c.source)}</Badge> : "—"),
    },
    {
      key: "added",
      header: "Added",
      align: "right",
      cell: (c) => <span className="text-muted-foreground text-xs">{formatDate(c.created_at)}</span>,
    },
  ];

  return (
    <>
      <PageHeader
        title="Candidates"
        description="Search, filter, and manage your entire talent pool."
        action={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={exportCsv} disabled={!rows.length}>
              <Download className="size-4" />
              Export
            </Button>
            {canManageCandidates && (
              <Button onClick={() => setUploadOpen(true)}>
                <Upload className="size-4" />
                Upload resumes
              </Button>
            )}
          </div>
        }
      />

      <FilterBar>
        <div className="relative min-w-[200px] flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => resetPageThen(() => setSearch(e.target.value))}
            placeholder="Search resumes (full-text)…"
            className="border-0 bg-transparent pl-8 shadow-none focus-visible:ring-0"
          />
        </div>
        <FilterSelect value={domainId} onChange={(v) => resetPageThen(() => setDomainId(v))} placeholder="Domain"
          options={[{ value: ALL, label: "All domains" }, ...(domains ?? []).map((d) => ({ value: d.id, label: d.name }))]} />
        <FilterSelect value={workMode} onChange={(v) => resetPageThen(() => setWorkMode(v))} placeholder="Work mode"
          options={[{ value: ALL, label: "Any mode" }, ...WORK_MODES.map((w) => ({ value: w, label: titleCase(w) }))]} />
        <FilterSelect value={source} onChange={(v) => resetPageThen(() => setSource(v))} placeholder="Source"
          options={[{ value: ALL, label: "All sources" }, ...SOURCES.map((s) => ({ value: s, label: titleCase(s) }))]} />
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm">
              <SlidersHorizontal className="size-4" /> Experience
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-56 space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Min experience (years)</Label>
              <Input type="number" min={0} value={minExp} onChange={(e) => resetPageThen(() => setMinExp(e.target.value))} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Max experience (years)</Label>
              <Input type="number" min={0} value={maxExp} onChange={(e) => resetPageThen(() => setMaxExp(e.target.value))} />
            </div>
          </PopoverContent>
        </Popover>
      </FilterBar>

      {selected.size > 0 && (
        <div className="bg-primary/5 text-primary mb-3 flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
          <span>{selected.size} selected</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={exportCsv}>
              <Download className="size-4" /> Export selected
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
          </div>
        </div>
      )}

      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        onRowClick={(r) => router.push(`/candidates/${r.id}`)}
        loading={loading}
        skeletonRows={10}
        empty={
          error ? (
            <EmptyState title="Couldn't load candidates" description={error} action={<Button variant="outline" onClick={reload}>Retry</Button>} />
          ) : (
            <EmptyState
              icon={<Users className="size-6" />}
              title="No candidates found"
              description="Try adjusting your filters, or upload resumes to get started."
              action={canManageCandidates ? <Button onClick={() => setUploadOpen(true)}><Upload className="size-4" /> Upload resumes</Button> : undefined}
            />
          )
        }
      />

      {rows.length > 0 && (
        <div className="mt-4 flex items-center justify-between">
          <p className="text-muted-foreground text-sm">
            {data?.total ?? 0} candidates · page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}

      <UploadResumesModal open={uploadOpen} onOpenChange={setUploadOpen} onUploaded={reload} />
    </>
  );
}

function FilterSelect({
  value,
  onChange,
  placeholder,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: { value: string; label: string }[];
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger size="sm" className="w-auto min-w-[130px] border-0 bg-transparent shadow-none">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
