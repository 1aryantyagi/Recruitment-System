"use client";

import { useState } from "react";
import { Plus, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { apiDelete, apiPost } from "@/lib/api";
import { useInterviewers, useRequisitionInterviewers } from "@/lib/meta";
import { AvatarName } from "@/components/common/avatar-name";
import { EmptyState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function AssignInterviewersPanel({
  requisitionId,
  canManage,
}: {
  requisitionId: string;
  canManage: boolean;
}) {
  const { data: assigned, loading, reload } = useRequisitionInterviewers(requisitionId);
  const { data: all } = useInterviewers();
  const [picked, setPicked] = useState("");
  const [busy, setBusy] = useState(false);

  const assignedIds = new Set((assigned ?? []).map((a) => a.interviewer?.id));
  const available = (all ?? []).filter((i) => !assignedIds.has(i.id));

  const add = async () => {
    if (!picked) return;
    setBusy(true);
    try {
      await apiPost(`/requisitions/${requisitionId}/interviewers`, { interviewer_id: picked });
      toast.success("Interviewer assigned");
      setPicked("");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (interviewerId: string) => {
    try {
      await apiDelete(`/requisitions/${requisitionId}/interviewers/${interviewerId}`);
      toast.success("Interviewer removed");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      {canManage && (
        <div className="flex gap-2">
          <Select value={picked} onValueChange={setPicked}>
            <SelectTrigger className="flex-1">
              <SelectValue placeholder="Select an interviewer to assign" />
            </SelectTrigger>
            <SelectContent>
              {available.length === 0 ? (
                <div className="text-muted-foreground px-2 py-2 text-sm">No more interviewers</div>
              ) : (
                available.map((i) => (
                  <SelectItem key={i.id} value={i.id}>
                    {i.name} · {i.email}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
          <Button onClick={add} disabled={!picked || busy}>
            <Plus className="size-4" /> Assign
          </Button>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : assigned && assigned.length > 0 ? (
        <div className="divide-y rounded-xl border">
          {assigned.map((a) => (
            <div key={a.id} className="flex items-center gap-3 px-3 py-2.5">
              <AvatarName name={a.interviewer?.name} subtitle={a.interviewer?.email} />
              {canManage && a.interviewer && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-destructive ml-auto"
                  onClick={() => remove(a.interviewer!.id)}
                  aria-label="Remove"
                >
                  <Trash2 className="size-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<UserPlus className="size-6" />}
          title="No interviewers assigned"
          description="Assign interviewers who can take rounds for this role."
        />
      )}
    </div>
  );
}
