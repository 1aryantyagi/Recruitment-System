"use client";

import { useEffect, useMemo, useState } from "react";
import { Columns3, Search } from "lucide-react";
import { toast } from "sonner";

import { apiList, apiPatch } from "@/lib/api";
import { useDebounce, useFetch } from "@/lib/hooks";
import type {
  ApplicationBoardItem,
  ApplicationStatus,
  ListResponse,
  RequisitionListItem,
} from "@/lib/types";
import { stageMeta } from "@/lib/labels";
import { PageHeader } from "@/components/common/page-header";
import { FilterBar } from "@/components/common/filter-bar";
import { EmptyState, ErrorState } from "@/components/common/states";
import { KanbanBoard } from "@/components/pipeline/kanban-board";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ALL = "__all__";

export default function PipelinePage() {
  const [reqId, setReqId] = useState(ALL);
  const [search, setSearch] = useState("");
  const debSearch = useDebounce(search, 350);

  const { data: reqs } = useFetch<ListResponse<RequisitionListItem>>(
    (signal) => apiList<RequisitionListItem>("/requisitions", { status: "OPEN", limit: 100 }, signal),
    [],
  );

  const query = useMemo(
    () => ({
      requisition_id: reqId === ALL ? undefined : reqId,
      search: debSearch || undefined,
      limit: 200,
    }),
    [reqId, debSearch],
  );

  const { data, loading, error, reload } = useFetch<ListResponse<ApplicationBoardItem>>(
    (signal) => apiList<ApplicationBoardItem>("/applications", query, signal),
    [JSON.stringify(query)],
  );

  const [items, setItems] = useState<ApplicationBoardItem[]>([]);
  useEffect(() => {
    if (data?.data) setItems(data.data);
  }, [data]);

  const onMove = async (id: string, toStatus: ApplicationStatus) => {
    const prev = items;
    setItems((cur) => cur.map((i) => (i.id === id ? { ...i, status: toStatus } : i)));
    try {
      await apiPatch(`/applications/${id}`, { status: toStatus });
      toast.success(`Moved to ${stageMeta(toStatus).label}`);
    } catch (err) {
      setItems(prev); // revert
      toast.error((err as Error).message || "Move failed");
    }
  };

  return (
    <>
      <PageHeader
        title="ATS Pipeline"
        description="Drag candidates across stages — changes persist instantly."
      />

      <FilterBar>
        <div className="relative min-w-[200px] flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search candidates…"
            className="border-0 bg-transparent pl-8 shadow-none focus-visible:ring-0"
          />
        </div>
        <Select value={reqId} onValueChange={setReqId}>
          <SelectTrigger size="sm" className="w-auto min-w-[200px] border-0 bg-transparent shadow-none">
            <SelectValue placeholder="Requisition" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All open roles</SelectItem>
            {(reqs?.data ?? []).map((r) => (
              <SelectItem key={r.id} value={r.id}>{r.title}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterBar>

      {loading ? (
        <div className="flex gap-4 overflow-hidden">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="w-[300px] shrink-0 space-y-2">
              <Skeleton className="h-6 w-32" />
              <Skeleton className="h-24 w-full rounded-xl" />
              <Skeleton className="h-24 w-full rounded-xl" />
            </div>
          ))}
        </div>
      ) : error ? (
        <ErrorState description={error} onRetry={reload} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Columns3 className="size-6" />}
          title="No candidates in this pipeline"
          description="Applications appear here once candidates are scored against open roles."
        />
      ) : (
        <KanbanBoard items={items} onMove={onMove} />
      )}
    </>
  );
}
