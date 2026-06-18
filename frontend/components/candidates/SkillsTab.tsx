"use client";

import { useEffect, useState } from "react";
import { Check, Plus, Trash2, BadgeCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { apiPost } from "@/lib/api";
import { cn, titleCase } from "@/lib/utils";
import type { CandidateDetail, CandidateSkill } from "@/lib/types";

export function SkillsTab({
  candidate,
  canEdit,
  onChanged,
}: {
  candidate: CandidateDetail;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [added, setAdded] = useState<string[]>([]);
  const [newSkill, setNewSkill] = useState("");
  const [saving, setSaving] = useState(false);

  // Seed confirmed with already-verified skills.
  useEffect(() => {
    setConfirmed(
      new Set(
        candidate.skills.filter((s) => s.is_verified).map((s) => s.skill_id),
      ),
    );
    setRemoved(new Set());
    setAdded([]);
  }, [candidate]);

  function toggleConfirm(skill: CandidateSkill) {
    setConfirmed((prev) => {
      const next = new Set(prev);
      if (next.has(skill.skill_id)) next.delete(skill.skill_id);
      else {
        next.add(skill.skill_id);
        setRemoved((r) => {
          const rn = new Set(r);
          rn.delete(skill.skill_id);
          return rn;
        });
      }
      return next;
    });
  }

  function toggleRemove(skill: CandidateSkill) {
    setRemoved((prev) => {
      const next = new Set(prev);
      if (next.has(skill.skill_id)) next.delete(skill.skill_id);
      else {
        next.add(skill.skill_id);
        setConfirmed((c) => {
          const cn = new Set(c);
          cn.delete(skill.skill_id);
          return cn;
        });
      }
      return next;
    });
  }

  function addSkill() {
    const v = newSkill.trim();
    if (!v) return;
    if (!added.includes(v)) setAdded((a) => [...a, v]);
    setNewSkill("");
  }

  const dirty = added.length > 0 || removed.size > 0 || confirmed.size > 0;

  async function save() {
    setSaving(true);
    try {
      await apiPost(`/candidates/${candidate.id}/confirm-skills`, {
        confirmed_skill_ids: Array.from(confirmed),
        removed_skill_ids: Array.from(removed),
        added_skill_names: added,
      });
      toast.success("Skills updated");
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      {candidate.skills.length === 0 && added.length === 0 ? (
        <EmptyState title="No skills extracted yet" />
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {candidate.skills.map((s) => {
            const isConfirmed = confirmed.has(s.skill_id);
            const isRemoved = removed.has(s.skill_id);
            return (
              <div
                key={s.id}
                className={cn(
                  "flex items-center justify-between gap-2 rounded-lg border px-3 py-2",
                  isRemoved
                    ? "border-red-200 bg-red-50 opacity-70"
                    : isConfirmed
                      ? "border-emerald-200 bg-emerald-50"
                      : "border-slate-200 bg-white",
                )}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        "truncate text-sm font-medium text-slate-700",
                        isRemoved && "line-through",
                      )}
                    >
                      {s.skill_name}
                    </span>
                    {s.is_verified && (
                      <BadgeCheck className="h-4 w-4 text-emerald-500" />
                    )}
                  </div>
                  <p className="text-xs text-slate-400">
                    {[
                      s.category && titleCase(s.category),
                      s.proficiency_level && titleCase(s.proficiency_level),
                      s.years_of_experience != null &&
                        `${s.years_of_experience} yrs`,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "—"}
                  </p>
                </div>
                {canEdit && (
                  <div className="flex shrink-0 gap-1">
                    <button
                      onClick={() => toggleConfirm(s)}
                      title="Confirm"
                      className={cn(
                        "rounded-md p-1.5 transition",
                        isConfirmed
                          ? "bg-emerald-600 text-white"
                          : "text-slate-400 hover:bg-slate-100",
                      )}
                    >
                      <Check className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => toggleRemove(s)}
                      title="Remove"
                      className={cn(
                        "rounded-md p-1.5 transition",
                        isRemoved
                          ? "bg-red-600 text-white"
                          : "text-slate-400 hover:bg-slate-100",
                      )}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {added.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {added.map((a) => (
            <Badge key={a} tone="indigo">
              + {a}
            </Badge>
          ))}
        </div>
      )}

      {canEdit && (
        <div className="space-y-3 border-t border-slate-100 pt-4">
          <div className="flex items-end gap-2">
            <Input
              label="Add a skill"
              value={newSkill}
              onChange={(e) => setNewSkill(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addSkill();
                }
              }}
              placeholder="e.g. Kubernetes"
            />
            <Button variant="outline" onClick={addSkill}>
              <Plus className="h-4 w-4" /> Add
            </Button>
          </div>
          <Button onClick={save} loading={saving} disabled={!dirty}>
            Save skill changes
          </Button>
        </div>
      )}
    </div>
  );
}
