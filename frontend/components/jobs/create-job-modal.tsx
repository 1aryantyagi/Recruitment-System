"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { apiPost } from "@/lib/api";
import { useDepartments, useDomains, useSkills } from "@/lib/meta";
import { titleCase } from "@/lib/utils";
import {
  SENIORITY_LEVELS,
  WORK_MODES,
  type RequisitionCreate,
  type RequisitionCreateSkill,
  type RequisitionDetail,
  type SeniorityLevel,
  type WorkMode,
} from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface SkillRow extends RequisitionCreateSkill {
  _key: string;
}

const NONE = "__none__";

export function CreateJobModal({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated?: () => void;
}) {
  const { skills } = useSkills();
  const { data: domains } = useDomains();
  const { data: departments } = useDepartments();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [domainId, setDomainId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [seniority, setSeniority] = useState("");
  const [location, setLocation] = useState("");
  const [workMode, setWorkMode] = useState("");
  const [minExp, setMinExp] = useState("");
  const [maxExp, setMaxExp] = useState("");
  const [minBudget, setMinBudget] = useState("");
  const [maxBudget, setMaxBudget] = useState("");
  const [openings, setOpenings] = useState("1");
  const [targetClose, setTargetClose] = useState("");
  const [skillRows, setSkillRows] = useState<SkillRow[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setTitle("");
    setDescription("");
    setDomainId("");
    setDepartmentId("");
    setSeniority("");
    setLocation("");
    setWorkMode("");
    setMinExp("");
    setMaxExp("");
    setMinBudget("");
    setMaxBudget("");
    setOpenings("1");
    setTargetClose("");
    setSkillRows([]);
  };

  const close = (v: boolean) => {
    if (submitting) return;
    if (!v) reset();
    onOpenChange(v);
  };

  const addSkillRow = () =>
    setSkillRows((rows) => [
      ...rows,
      { _key: crypto.randomUUID(), skill_id: "", is_mandatory: true },
    ]);

  const updateSkillRow = (key: string, patch: Partial<SkillRow>) =>
    setSkillRows((rows) =>
      rows.map((r) => (r._key === key ? { ...r, ...patch } : r)),
    );

  const removeSkillRow = (key: string) =>
    setSkillRows((rows) => rows.filter((r) => r._key !== key));

  const submit = async () => {
    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }
    setSubmitting(true);
    try {
      const cleanSkills: RequisitionCreateSkill[] = skillRows
        .filter((r) => r.skill_id)
        .map((r) => ({
          skill_id: r.skill_id,
          is_mandatory: r.is_mandatory,
          minimum_years: r.minimum_years,
        }));

      const body: RequisitionCreate = {
        title: title.trim(),
        description: description.trim() || undefined,
        domain_id: domainId || undefined,
        department_id: departmentId || undefined,
        seniority_level: (seniority || undefined) as SeniorityLevel | undefined,
        location: location.trim() || undefined,
        work_mode: (workMode || undefined) as WorkMode | undefined,
        min_experience_years: minExp ? Number(minExp) : undefined,
        max_experience_years: maxExp ? Number(maxExp) : undefined,
        min_budget_ctc: minBudget ? Number(minBudget) : undefined,
        max_budget_ctc: maxBudget ? Number(maxBudget) : undefined,
        number_of_openings: openings ? Number(openings) : 1,
        target_close_date: targetClose || undefined,
        skills: cleanSkills,
      };

      await apiPost<RequisitionDetail>("/requisitions", body);
      toast.success("Requisition created");
      reset();
      onOpenChange(false);
      onCreated?.();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90vh] gap-0 overflow-hidden p-0 sm:max-w-3xl">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>Create requisition</DialogTitle>
          <DialogDescription>
            Open a new role and define what a great match looks like.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[calc(90vh-9.5rem)] space-y-5 overflow-y-auto px-6 py-5">
          <Field label="Title" required>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Senior Backend Engineer"
              autoFocus
            />
          </Field>

          <Field label="Description">
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Role summary, responsibilities, and the ideal candidate…"
              rows={4}
            />
          </Field>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Domain">
              <PickerSelect
                value={domainId}
                onChange={setDomainId}
                placeholder="Select domain"
                options={(domains ?? []).map((d) => ({ value: d.id, label: d.name }))}
              />
            </Field>
            <Field label="Department">
              <PickerSelect
                value={departmentId}
                onChange={setDepartmentId}
                placeholder="Select department"
                options={(departments ?? []).map((d) => ({ value: d.id, label: d.name }))}
              />
            </Field>
            <Field label="Seniority">
              <PickerSelect
                value={seniority}
                onChange={setSeniority}
                placeholder="Select level"
                options={SENIORITY_LEVELS.map((s) => ({ value: s, label: titleCase(s) }))}
              />
            </Field>
            <Field label="Location">
              <Input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. Bengaluru"
              />
            </Field>
            <Field label="Work mode">
              <PickerSelect
                value={workMode}
                onChange={setWorkMode}
                placeholder="Select mode"
                options={WORK_MODES.map((w) => ({ value: w, label: titleCase(w) }))}
              />
            </Field>
            <Field label="Openings">
              <Input
                type="number"
                min={1}
                value={openings}
                onChange={(e) => setOpenings(e.target.value)}
              />
            </Field>
            <Field label="Min experience (yrs)">
              <Input
                type="number"
                min={0}
                value={minExp}
                onChange={(e) => setMinExp(e.target.value)}
              />
            </Field>
            <Field label="Max experience (yrs)">
              <Input
                type="number"
                min={0}
                value={maxExp}
                onChange={(e) => setMaxExp(e.target.value)}
              />
            </Field>
            <Field label="Target close date">
              <Input
                type="date"
                value={targetClose}
                onChange={(e) => setTargetClose(e.target.value)}
              />
            </Field>
            <Field label="Min budget (CTC)">
              <Input
                type="number"
                min={0}
                value={minBudget}
                onChange={(e) => setMinBudget(e.target.value)}
              />
            </Field>
            <Field label="Max budget (CTC)">
              <Input
                type="number"
                min={0}
                value={maxBudget}
                onChange={(e) => setMaxBudget(e.target.value)}
              />
            </Field>
          </div>

          {/* Skills */}
          <div className="border-t pt-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-semibold">Required skills</h4>
                <p className="text-muted-foreground text-xs">
                  Used to score and rank the candidate pool.
                </p>
              </div>
              <Button type="button" variant="outline" size="sm" onClick={addSkillRow}>
                <Plus className="size-4" /> Add skill
              </Button>
            </div>

            {skillRows.length === 0 ? (
              <p className="text-muted-foreground rounded-lg border border-dashed px-3 py-4 text-center text-xs">
                No skills added yet.
              </p>
            ) : (
              <div className="space-y-2">
                {skillRows.map((row) => (
                  <div
                    key={row._key}
                    className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[1fr_7rem_auto_auto]"
                  >
                    <PickerSelect
                      value={row.skill_id ?? ""}
                      onChange={(v) => updateSkillRow(row._key, { skill_id: v })}
                      placeholder="Select skill"
                      clearable={false}
                      options={skills.map((s) => ({ value: s.id, label: s.name }))}
                    />
                    <Input
                      type="number"
                      min={0}
                      placeholder="Min yrs"
                      value={row.minimum_years ?? ""}
                      onChange={(e) =>
                        updateSkillRow(row._key, {
                          minimum_years: e.target.value
                            ? Number(e.target.value)
                            : undefined,
                        })
                      }
                    />
                    <label className="flex h-9 cursor-pointer items-center gap-2 px-1 text-xs font-medium whitespace-nowrap">
                      <Checkbox
                        checked={row.is_mandatory}
                        onCheckedChange={(v) =>
                          updateSkillRow(row._key, { is_mandatory: !!v })
                        }
                      />
                      Mandatory
                    </label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => removeSkillRow(row._key)}
                      aria-label="Remove skill"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="border-t px-6 py-4">
          <Button variant="outline" onClick={() => close(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={submitting || !title.trim()}>
            {submitting ? "Creating…" : "Create requisition"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">
        {label}
        {required && <span className="text-destructive"> *</span>}
      </Label>
      {children}
    </div>
  );
}

function PickerSelect({
  value,
  onChange,
  placeholder,
  options,
  clearable = true,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: { value: string; label: string }[];
  clearable?: boolean;
}) {
  return (
    <Select
      value={value || NONE}
      onValueChange={(v) => onChange(v === NONE ? "" : v)}
    >
      <SelectTrigger className="w-full">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {clearable && <SelectItem value={NONE}>{placeholder}</SelectItem>}
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
