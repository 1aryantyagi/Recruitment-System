"use client";

import { useState } from "react";
import { Loader2, Plus, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useFetch } from "@/lib/hooks";
import { useInterviewers, useInterviewerSlots } from "@/lib/meta";
import type { Interviewer, InterviewerSlot, User } from "@/lib/types";
import { titleCase } from "@/lib/utils";
import { PageHeader } from "@/components/common/page-header";
import { AvatarName } from "@/components/common/avatar-name";
import { DataTable, type Column } from "@/components/common/data-table";
import { EmptyState, TableSkeleton } from "@/components/common/states";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DEFAULT_MASK = 0b0011111;

export default function TeamPage() {
  const { isAdmin } = useAuth();
  return (
    <>
      <PageHeader title="Team" description="Members, interviewers, and availability." />
      <Tabs defaultValue="members">
        <TabsList>
          <TabsTrigger value="members">Members</TabsTrigger>
          <TabsTrigger value="availability">Availability</TabsTrigger>
        </TabsList>
        <TabsContent value="members" className="mt-4">
          <MembersTab isAdmin={isAdmin} />
        </TabsContent>
        <TabsContent value="availability" className="mt-4">
          <AvailabilityTab canManage={isAdmin} />
        </TabsContent>
      </Tabs>
    </>
  );
}

function MembersTab({ isAdmin }: { isAdmin: boolean }) {
  const users = useFetch<User[]>((s) => apiGet<User[]>("/users", undefined, s), [], { enabled: isAdmin });
  const interviewers = useInterviewers();
  const [addOpen, setAddOpen] = useState(false);

  const list: (User | Interviewer)[] = isAdmin ? users.data ?? [] : interviewers.data ?? [];
  const loading = isAdmin ? users.loading : interviewers.loading;
  const reload = isAdmin ? users.reload : interviewers.reload;

  const columns: Column<User | Interviewer>[] = [
    { key: "name", header: "Member", cell: (u) => <AvatarName name={u.name} subtitle={u.email} /> },
    { key: "role", header: "Role", cell: (u) => <Badge variant="secondary">{titleCase(u.role)}</Badge> },
    { key: "interviewer", header: "Interviewer", cell: (u) => (u.is_interviewer ? <Badge variant="info">Yes</Badge> : <span className="text-muted-foreground">No</span>) },
    {
      key: "status",
      header: "Status",
      cell: (u) =>
        "is_active" in u && !(u as User).is_active ? (
          <Badge variant="muted">Inactive</Badge>
        ) : (
          <Badge variant="success">Active</Badge>
        ),
    },
  ];

  return (
    <>
      <div className="mb-3 flex justify-end">
        {isAdmin && (
          <Button onClick={() => setAddOpen(true)}>
            <UserPlus className="size-4" /> Add member
          </Button>
        )}
      </div>
      <DataTable
        columns={columns}
        rows={list}
        getRowId={(u) => u.id}
        loading={loading}
        empty={<EmptyState title="No members" description="No team members to show." />}
      />
      {isAdmin && <AddMemberDialog open={addOpen} onOpenChange={setAddOpen} onAdded={reload} />}
    </>
  );
}

function AddMemberDialog({ open, onOpenChange, onAdded }: { open: boolean; onOpenChange: (v: boolean) => void; onAdded: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("HR");
  const [isInterviewer, setIsInterviewer] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await apiPost("/auth/users", { name, email, password, role, is_interviewer: isInterviewer });
      toast.success("Member added");
      onAdded();
      onOpenChange(false);
      setName(""); setEmail(""); setPassword("");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add team member</DialogTitle>
          <DialogDescription>Create a new user account with a role.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Name</Label><Input value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div className="space-y-1.5"><Label>Temporary password</Label><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Role</Label>
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["HR", "DELIVERY_MANAGER", "ADMIN"].map((r) => <SelectItem key={r} value={r}>{titleCase(r)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={isInterviewer} onChange={(e) => setIsInterviewer(e.target.checked)} className="size-4 rounded border" />
                Is interviewer
              </label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy || !name || !email || !password}>
            {busy && <Loader2 className="size-4 animate-spin" />} Add member
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AvailabilityTab({ canManage }: { canManage: boolean }) {
  const { data: interviewers } = useInterviewers();
  const [interviewerId, setInterviewerId] = useState("");
  const { data: slots, loading, reload } = useInterviewerSlots(interviewerId);

  const [time, setTime] = useState("16:30");
  const [mask, setMask] = useState(DEFAULT_MASK);
  const [duration, setDuration] = useState(60);
  const [busy, setBusy] = useState(false);

  const addSlot = async () => {
    if (!interviewerId) return toast.error("Select an interviewer first");
    setBusy(true);
    try {
      await apiPost(`/interviewers/${interviewerId}/slots`, { slot_time: time, weekday_mask: mask, duration_minutes: duration });
      toast.success("Slot added");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (slotId: string) => {
    try {
      await apiDelete(`/interviewers/${interviewerId}/slots/${slotId}`);
      toast.success("Slot removed");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const maskLabel = (m: number) => WEEKDAYS.filter((_, i) => (m >> i) & 1).join(", ") || "—";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <Card className="gap-4 p-5 lg:col-span-1">
        <h3 className="text-sm font-semibold">Interviewer</h3>
        <Select value={interviewerId} onValueChange={setInterviewerId}>
          <SelectTrigger><SelectValue placeholder="Select interviewer" /></SelectTrigger>
          <SelectContent>
            {(interviewers ?? []).map((i) => <SelectItem key={i.id} value={i.id}>{i.name}</SelectItem>)}
          </SelectContent>
        </Select>
        {canManage && interviewerId && (
          <>
            <div className="space-y-1.5"><Label>Time</Label><Input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></div>
            <div className="space-y-1.5">
              <Label>Weekdays</Label>
              <div className="flex flex-wrap gap-1">
                {WEEKDAYS.map((d, i) => (
                  <button
                    key={d}
                    onClick={() => setMask((m) => m ^ (1 << i))}
                    className={`rounded-md border px-2 py-1 text-xs font-medium ${(mask >> i) & 1 ? "border-primary bg-primary text-primary-foreground" : "bg-muted/40"}`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5"><Label>Duration (min)</Label><Input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></div>
            <Button onClick={addSlot} disabled={busy}><Plus className="size-4" /> Add slot</Button>
          </>
        )}
      </Card>

      <Card className="gap-0 p-0 lg:col-span-2">
        <div className="border-b p-5"><h3 className="text-sm font-semibold">Recurring availability</h3></div>
        {!interviewerId ? (
          <p className="text-muted-foreground p-8 text-center text-sm">Select an interviewer to view their slots.</p>
        ) : loading ? (
          <div className="p-5"><TableSkeleton rows={3} cols={3} /></div>
        ) : slots && slots.length ? (
          <div className="divide-y">
            {slots.map((s: InterviewerSlot) => (
              <div key={s.id} className="flex items-center gap-3 px-5 py-3">
                <span className="font-medium tabular-nums">{s.slot_time}</span>
                <span className="text-muted-foreground text-sm">{maskLabel(s.weekday_mask)}</span>
                <Badge variant="muted" className="ml-2">{s.duration_minutes}m</Badge>
                {canManage && (
                  <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-destructive ml-auto" onClick={() => remove(s.id)}>
                    <Trash2 className="size-4" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground p-8 text-center text-sm">No availability slots configured.</p>
        )}
      </Card>
    </div>
  );
}
