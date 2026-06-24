"use client";

import { useState } from "react";
import { CheckCircle2, Loader2, Mail, Plus, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useFetch } from "@/lib/hooks";
import { useSkills } from "@/lib/meta";
import { formatDateTime, titleCase } from "@/lib/utils";
import { PageHeader } from "@/components/common/page-header";
import { Stat } from "@/components/common/stat";
import { InitialsAvatar } from "@/components/common/avatar-name";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface GmailStatus {
  auth_mode?: string | null;
  connected_email?: string | null;
  disabled?: boolean;
  last_error?: string | null;
  last_synced_at?: string | null;
}

export default function SettingsPage() {
  const { user, isAdmin } = useAuth();

  return (
    <>
      <PageHeader title="Settings" description="Your profile, integrations, and the skills catalog." />
      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
          <TabsTrigger value="skills">Skills</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="mt-4">
          <Card className="gap-5 p-6">
            <div className="flex items-center gap-4">
              <InitialsAvatar name={user?.name} size="lg" />
              <div>
                <h3 className="text-lg font-semibold">{user?.name}</h3>
                <p className="text-muted-foreground text-sm">{user?.email}</p>
              </div>
              <Badge variant="muted" className="ml-auto">{titleCase(user?.role)}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-5 border-t pt-5 sm:grid-cols-3">
              <Stat label="Role" value={titleCase(user?.role)} />
              <Stat label="Interviewer" value={user?.is_interviewer ? "Yes" : "No"} />
              <Stat label="Status" value={user?.is_active ? "Active" : "Inactive"} />
            </div>
            <p className="text-muted-foreground text-xs">
              Appearance (light / dark / system) can be changed from the theme toggle in the top bar.
            </p>
          </Card>
        </TabsContent>

        <TabsContent value="integrations" className="mt-4">
          {isAdmin ? <GmailIntegration /> : <AdminOnly />}
        </TabsContent>

        <TabsContent value="skills" className="mt-4">
          <SkillsCatalog isAdmin={isAdmin} />
        </TabsContent>
      </Tabs>
    </>
  );
}

function AdminOnly() {
  return (
    <Card className="items-center gap-2 p-10 text-center">
      <ShieldAlert className="text-muted-foreground mx-auto size-8" />
      <p className="text-sm font-medium">Admin access required</p>
      <p className="text-muted-foreground text-sm">Only administrators can manage this section.</p>
    </Card>
  );
}

function GmailIntegration() {
  const { data, loading, reload } = useFetch<GmailStatus>(
    (s) => apiGet<GmailStatus>("/integrations/gmail/status", undefined, s),
    [],
  );
  const [busy, setBusy] = useState(false);
  const connected = !!data?.connected_email && !data?.disabled;

  const connect = async () => {
    setBusy(true);
    try {
      const res = await apiGet<{ url?: string; auth_url?: string }>("/integrations/gmail/connect");
      const url = res.url ?? res.auth_url;
      if (url) window.location.href = url;
    } catch (err) {
      toast.error((err as Error).message);
      setBusy(false);
    }
  };
  const disconnect = async () => {
    setBusy(true);
    try {
      await apiPost("/integrations/gmail/disconnect");
      toast.success("Gmail disconnected");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="gap-4 p-6">
      <div className="flex items-start gap-3">
        <span className="bg-primary/10 text-primary flex size-10 items-center justify-center rounded-xl">
          <Mail className="size-5" />
        </span>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Gmail resume ingestion</h3>
            {loading ? null : connected ? (
              <Badge variant="success" className="gap-1"><CheckCircle2 className="size-3" /> Connected</Badge>
            ) : (
              <Badge variant="muted">Not connected</Badge>
            )}
          </div>
          <p className="text-muted-foreground text-sm">
            Auto-ingest resume attachments from a mailbox every 5 minutes.
          </p>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <div className="bg-muted/40 grid grid-cols-2 gap-4 rounded-lg border p-4 text-sm sm:grid-cols-3">
          <Stat label="Mailbox" value={data?.connected_email ?? "—"} />
          <Stat label="Auth mode" value={data?.auth_mode ?? "—"} />
          <Stat label="Last synced" value={data?.last_synced_at ? formatDateTime(data.last_synced_at) : "—"} />
        </div>
      )}
      {data?.last_error && (
        <p className="text-destructive text-xs">Last error: {data.last_error}</p>
      )}

      <div className="flex gap-2">
        {connected ? (
          <Button variant="outline" onClick={disconnect} disabled={busy}>
            {busy && <Loader2 className="size-4 animate-spin" />} Disconnect
          </Button>
        ) : (
          <Button onClick={connect} disabled={busy}>
            {busy && <Loader2 className="size-4 animate-spin" />} Connect Gmail
          </Button>
        )}
      </div>
    </Card>
  );
}

function SkillsCatalog({ isAdmin }: { isAdmin: boolean }) {
  const { byCategory, loading } = useSkills();
  const [name, setName] = useState("");
  const [category, setCategory] = useState("TOOL");
  const [busy, setBusy] = useState(false);

  const CATEGORIES = ["PROGRAMMING_LANGUAGE", "FRAMEWORK", "CLOUD", "DATABASE", "TOOL", "DOMAIN_SKILL", "SOFT_SKILL"];

  const add = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await apiPost("/skills", { name: name.trim(), category });
      toast.success("Skill added — refresh to see it");
      setName("");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {isAdmin && (
        <Card className="flex-row flex-wrap items-end gap-3 p-4">
          <div className="min-w-[180px] flex-1 space-y-1.5">
            <Label>New skill</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Kubernetes" />
          </div>
          <div className="space-y-1.5">
            <Label>Category</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="w-[180px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{titleCase(c)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={add} disabled={busy || !name.trim()}><Plus className="size-4" /> Add</Button>
        </Card>
      )}

      {loading ? (
        <Skeleton className="h-64 w-full rounded-xl" />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Object.entries(byCategory).map(([cat, skills]) => (
            <Card key={cat} className="gap-3 p-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">{titleCase(cat)}</h3>
                <Badge variant="muted">{skills.length}</Badge>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {skills.map((s) => (
                  <Badge key={s.id} variant={s.is_verified ? "secondary" : "outline"}>{s.name}</Badge>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
