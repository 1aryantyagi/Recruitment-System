"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";
import { useSkills, useDomains, useDepartments } from "@/lib/meta";
import { apiPost } from "@/lib/api";
import { titleCase } from "@/lib/utils";
import {
  SENIORITY_LEVELS,
  WORK_MODES,
  type RequisitionCreate,
  type RequisitionCreateSkill,
  type RequisitionDetail,
} from "@/lib/types";

interface SkillRow extends RequisitionCreateSkill {
  _key: string;
}

export function CreateJobModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
}) {
  const toast = useToast();
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

  function addSkillRow() {
    setSkillRows((rows) => [
      ...rows,
      { _key: crypto.randomUUID(), skill_id: "", is_mandatory: true },
    ]);
  }

  function updateSkillRow(key: string, patch: Partial<SkillRow>) {
    setSkillRows((rows) =>
      rows.map((r) => (r._key === key ? { ...r, ...patch } : r)),
    );
  }

  function removeSkillRow(key: string) {
    setSkillRows((rows) => rows.filter((r) => r._key !== key));
  }

  async function submit() {
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
        description: description || undefined,
        domain_id: domainId || undefined,
        department_id: departmentId || undefined,
        seniority_level: (seniority || undefined) as never,
        location: location || undefined,
        work_mode: (workMode || undefined) as never,
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
      onCreated?.();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create requisition"
      size="xl"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={submit} loading={submitting}>
            Create
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="Title *"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Senior Backend Engineer"
        />
        <Textarea
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Select
            label="Domain"
            options={(domains ?? []).map((d) => ({
              value: d.id,
              label: d.name,
            }))}
            value={domainId}
            onChange={(e) => setDomainId(e.target.value)}
            placeholder="—"
          />
          <Select
            label="Department"
            options={(departments ?? []).map((d) => ({
              value: d.id,
              label: d.name,
            }))}
            value={departmentId}
            onChange={(e) => setDepartmentId(e.target.value)}
            placeholder="—"
          />
          <Select
            label="Seniority"
            options={SENIORITY_LEVELS.map((s) => ({
              value: s,
              label: titleCase(s),
            }))}
            value={seniority}
            onChange={(e) => setSeniority(e.target.value)}
            placeholder="—"
          />
          <Input
            label="Location"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
          <Select
            label="Work mode"
            options={WORK_MODES.map((w) => ({ value: w, label: titleCase(w) }))}
            value={workMode}
            onChange={(e) => setWorkMode(e.target.value)}
            placeholder="—"
          />
          <Input
            label="Openings"
            type="number"
            min={1}
            value={openings}
            onChange={(e) => setOpenings(e.target.value)}
          />
          <Input
            label="Min experience (yrs)"
            type="number"
            value={minExp}
            onChange={(e) => setMinExp(e.target.value)}
          />
          <Input
            label="Max experience (yrs)"
            type="number"
            value={maxExp}
            onChange={(e) => setMaxExp(e.target.value)}
          />
          <Input
            label="Target close date"
            type="date"
            value={targetClose}
            onChange={(e) => setTargetClose(e.target.value)}
          />
          <Input
            label="Min budget (CTC)"
            type="number"
            value={minBudget}
            onChange={(e) => setMinBudget(e.target.value)}
          />
          <Input
            label="Max budget (CTC)"
            type="number"
            value={maxBudget}
            onChange={(e) => setMaxBudget(e.target.value)}
          />
        </div>

        {/* Skills picker */}
        <div className="border-t border-slate-100 pt-4">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-700">
              Required skills
            </h4>
            <Button variant="outline" size="sm" onClick={addSkillRow}>
              <Plus className="h-4 w-4" /> Add skill
            </Button>
          </div>
          {skillRows.length === 0 && (
            <p className="text-xs text-slate-400">No skills added.</p>
          )}
          <div className="space-y-2">
            {skillRows.map((row) => (
              <div
                key={row._key}
                className="grid grid-cols-1 items-end gap-2 sm:grid-cols-[1fr_auto_auto_auto]"
              >
                <Select
                  options={skills.map((s) => ({ value: s.id, label: s.name }))}
                  value={row.skill_id ?? ""}
                  onChange={(e) =>
                    updateSkillRow(row._key, { skill_id: e.target.value })
                  }
                  placeholder="Select skill"
                />
                <Input
                  type="number"
                  placeholder="Min yrs"
                  className="w-24"
                  value={row.minimum_years ?? ""}
                  onChange={(e) =>
                    updateSkillRow(row._key, {
                      minimum_years: e.target.value
                        ? Number(e.target.value)
                        : undefined,
                    })
                  }
                />
                <label className="flex h-10 items-center gap-1.5 whitespace-nowrap text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={row.is_mandatory}
                    onChange={(e) =>
                      updateSkillRow(row._key, {
                        is_mandatory: e.target.checked,
                      })
                    }
                  />
                  Mandatory
                </label>
                <button
                  onClick={() => removeSkillRow(row._key)}
                  className="flex h-10 items-center justify-center rounded-md px-2 text-slate-400 hover:bg-slate-100 hover:text-red-600"
                  aria-label="Remove skill"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
