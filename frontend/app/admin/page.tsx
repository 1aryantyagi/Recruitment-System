"use client";

import { useEffect, useState } from "react";
import { Plus, UserPlus, Tag, Mail } from "lucide-react";
import { AppShell, PageHeader } from "@/components/AppShell";
import { Card, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { Tabs, type TabDef } from "@/components/ui/Tabs";
import { Modal } from "@/components/ui/Modal";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/Table";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/lib/auth";
import { apiGet, apiPost } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import { useSkills } from "@/lib/meta";
import { titleCase } from "@/lib/utils";
import type { User, Skill } from "@/lib/types";

export default function AdminPage() {
  return (
    <AppShell>
      <AdminContent />
    </AppShell>
  );
}

function AdminContent() {
  const { isAdmin } = useAuth();
  const [tab, setTab] = useState("users");

  if (!isAdmin) {
    return (
      <EmptyState
        title="Access denied"
        description="Admin privileges are required to view this page."
      />
    );
  }

  const tabs: TabDef[] = [
    { key: "users", label: "Users" },
    { key: "skills", label: "Skills" },
    { key: "integrations", label: "Integrations" },
  ];

  return (
    <div className="space-y-5">
      <PageHeader title="Admin" description="Manage users, the skill catalog, and integrations" />
      <Card>
        <Tabs tabs={tabs} active={tab} onChange={setTab} className="px-3" />
        <CardBody>
          {tab === "users" ? (
            <UsersPanel />
          ) : tab === "skills" ? (
            <SkillsPanel />
          ) : (
            <IntegrationsPanel />
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function UsersPanel() {
  const [createOpen, setCreateOpen] = useState(false);
  const { data, loading, error, reload } = useFetch<User[]>(
    () => apiGet<User[]>("/users"),
    [],
  );

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreateOpen(true)}>
          <UserPlus className="h-4 w-4" /> Add interviewer
        </Button>
      </div>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data || data.length === 0 ? (
        <EmptyState title="No users found" />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Email</TH>
              <TH>Role</TH>
              <TH>Interviewer</TH>
              <TH>Active</TH>
            </TR>
          </THead>
          <TBody>
            {data.map((u) => (
              <TR key={u.id} className="hover:bg-slate-50">
                <TD className="font-medium text-slate-700">{u.name}</TD>
                <TD>{u.email}</TD>
                <TD>
                  <Badge tone="indigo">{titleCase(u.role)}</Badge>
                </TD>
                <TD>{u.is_interviewer ? "Yes" : "No"}</TD>
                <TD>
                  {u.is_active ? (
                    <Badge tone="green">Active</Badge>
                  ) : (
                    <Badge tone="gray">Inactive</Badge>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <CreateInterviewerModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={reload}
      />
    </div>
  );
}

function CreateInterviewerModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("HR");
  const [isInterviewer, setIsInterviewer] = useState(true);
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (!name.trim() || !email.trim() || !password) {
      toast.error("Name, email and password are required");
      return;
    }
    setSaving(true);
    try {
      await apiPost("/interviewers", {
        name: name.trim(),
        email: email.trim(),
        password,
        role,
        is_interviewer: isInterviewer,
      });
      toast.success("User created");
      onCreated();
      onClose();
      setName("");
      setEmail("");
      setPassword("");
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
      title="Add interviewer / user"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} loading={saving}>
            Create
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Select
          label="Role"
          options={[
            { value: "HR", label: "HR" },
            { value: "DELIVERY_MANAGER", label: "Delivery Manager" },
            { value: "ADMIN", label: "Admin" },
          ]}
          value={role}
          onChange={(e) => setRole(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={isInterviewer}
            onChange={(e) => setIsInterviewer(e.target.checked)}
          />
          Can be assigned as interviewer
        </label>
      </div>
    </Modal>
  );
}

function SkillsPanel() {
  const { byCategory, loading, error } = useSkills();
  const [addOpen, setAddOpen] = useState(false);
  const [aliasFor, setAliasFor] = useState<Skill | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // useSkills doesn't expose reload; remount via key by re-reading on demand.
  // Simplest: reload page data through a key on the panel.
  void refreshKey;

  const categories = Object.entries(byCategory);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setAddOpen(true)}>
          <Plus className="h-4 w-4" /> Add skill
        </Button>
      </div>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} />
      ) : categories.length === 0 ? (
        <EmptyState title="No skills in catalog" />
      ) : (
        <div className="space-y-5">
          {categories.map(([category, skills]) => (
            <div key={category}>
              <h4 className="mb-2 text-sm font-semibold text-slate-700">
                {titleCase(category)}{" "}
                <span className="text-xs font-normal text-slate-400">
                  ({skills.length})
                </span>
              </h4>
              <div className="flex flex-wrap gap-2">
                {skills.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setAliasFor(s)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 transition hover:border-indigo-300 hover:bg-indigo-50"
                  >
                    <Tag className="h-3 w-3 text-slate-400" />
                    {s.name}
                    {s.is_verified && (
                      <span className="text-emerald-500">✓</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <AddSkillModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={() => setRefreshKey((k) => k + 1)}
      />
      {aliasFor && (
        <AddAliasModal
          open={!!aliasFor}
          onClose={() => setAliasFor(null)}
          skill={aliasFor}
        />
      )}
    </div>
  );
}

function AddSkillModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (!name.trim() || !category.trim()) {
      toast.error("Name and category are required");
      return;
    }
    setSaving(true);
    try {
      await apiPost("/skills", { name: name.trim(), category: category.trim() });
      toast.success("Skill added — reload to see it in catalog");
      onCreated();
      onClose();
      setName("");
      setCategory("");
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
      title="Add skill"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} loading={saving}>
            Add
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Input
          label="Skill name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          label="Category"
          placeholder="e.g. PROGRAMMING_LANGUAGE"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
      </div>
    </Modal>
  );
}

function AddAliasModal({
  open,
  onClose,
  skill,
}: {
  open: boolean;
  onClose: () => void;
  skill: Skill;
}) {
  const toast = useToast();
  const [aliases, setAliases] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    const list = aliases
      .split(",")
      .map((a) => a.trim())
      .filter(Boolean);
    if (list.length === 0) {
      toast.error("Enter at least one alias");
      return;
    }
    setSaving(true);
    try {
      await apiPost(`/skills/${skill.id}/aliases`, { aliases: list });
      toast.success("Aliases added");
      onClose();
      setAliases("");
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
      title={`Aliases for ${skill.name}`}
      description="Comma-separated alternate names."
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} loading={saving}>
            Save
          </Button>
        </>
      }
    >
      <Input
        label="Aliases"
        placeholder="e.g. JS, ECMAScript"
        value={aliases}
        onChange={(e) => setAliases(e.target.value)}
      />
    </Modal>
  );
}

type GmailStatus = {
  configured: boolean;
  connected: boolean;
  auth_mode: string;
  connected_email: string | null;
  disabled: boolean;
  last_error: string | null;
  last_synced_at: string | null;
  poll_interval_minutes: number;
  backed_off: boolean;
};

function IntegrationsPanel() {
  const toast = useToast();
  const { data, loading, error, reload } = useFetch<GmailStatus>(
    () => apiGet<GmailStatus>("/integrations/gmail/status"),
    [],
  );
  const [busy, setBusy] = useState(false);

  // Surface the OAuth callback result (?gmail=connected|error) once on return.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("gmail");
    if (!result) return;
    if (result === "connected") toast.success("Gmail connected");
    else toast.error("Gmail connection failed — please try again");
    window.history.replaceState({}, "", window.location.pathname);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connect() {
    setBusy(true);
    try {
      const { authorization_url } = await apiGet<{ authorization_url: string }>(
        "/integrations/gmail/connect",
      );
      window.location.href = authorization_url;
    } catch (err) {
      toast.error((err as Error).message);
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      await apiPost("/integrations/gmail/disconnect", {});
      toast.success("Gmail disconnected");
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={reload} />;

  const connected = !!data?.connected && !data?.disabled;
  const mode = data?.auth_mode ?? "none";

  return (
    <div className="space-y-4">
      <div>
        <h4 className="mb-1 text-sm font-semibold text-slate-700">
          Gmail resume intake
        </h4>
        <p className="text-xs text-slate-500">
          Auto-ingest resumes from unread Gmail messages every{" "}
          {data?.poll_interval_minutes ?? 5} min.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <Mail className="h-5 w-5 text-slate-400" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {connected ? (
              <Badge tone="green">Connected</Badge>
            ) : data?.disabled ? (
              <Badge tone="red">Needs reconnect</Badge>
            ) : (
              <Badge tone="gray">Not connected</Badge>
            )}
            <span className="text-xs text-slate-400">mode: {mode}</span>
          </div>
          {data?.connected_email && (
            <div className="mt-1 truncate text-sm text-slate-600">
              {data.connected_email}
            </div>
          )}
          {data?.last_error && (
            <div className="mt-1 truncate text-xs text-red-500">
              Last error: {data.last_error}
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {mode === "service_account" ? (
            <span className="text-xs text-slate-400">
              Configured via service account
            </span>
          ) : (
            <>
              <Button onClick={connect} loading={busy}>
                <Mail className="h-4 w-4" />{" "}
                {connected ? "Reconnect" : "Connect Gmail"}
              </Button>
              {(connected || data?.disabled) && (
                <Button variant="outline" onClick={disconnect} disabled={busy}>
                  Disconnect
                </Button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
