"use client";

import { useRef, useState } from "react";
import { Upload, FileCheck2, FileX2, Loader2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { apiUpload } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { UploadResponse, UploadResultItem } from "@/lib/types";

const SOURCES = [
  "REFERRAL",
  "JOB_BOARD",
  "LINKEDIN",
  "AGENCY",
  "DIRECT",
  "OTHER",
];

export function UploadResumesModal({
  open,
  onClose,
  onUploaded,
}: {
  open: boolean;
  onClose: () => void;
  onUploaded?: () => void;
}) {
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [source, setSource] = useState("");
  const [sourceDetail, setSourceDetail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState<UploadResultItem[] | null>(null);

  function reset() {
    setFiles([]);
    setEmail("");
    setFullName("");
    setSource("");
    setSourceDetail("");
    setResults(null);
  }

  function handleClose() {
    if (submitting) return;
    reset();
    onClose();
  }

  async function submit() {
    if (files.length === 0) {
      toast.error("Select at least one resume file");
      return;
    }
    setSubmitting(true);
    setResults(null);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      if (email.trim()) fd.append("email", email.trim());
      if (fullName.trim()) fd.append("full_name", fullName.trim());
      if (source) fd.append("source", source);
      if (sourceDetail.trim()) fd.append("source_detail", sourceDetail.trim());

      const res = await apiUpload<UploadResponse>("/candidates", fd);
      setResults(res.results ?? []);
      const ok = (res.results ?? []).filter((r) => !r.error).length;
      const fail = (res.results ?? []).filter((r) => r.error).length;
      if (ok > 0) toast.success(`${ok} resume(s) processed`);
      if (fail > 0) toast.error(`${fail} resume(s) failed`);
      onUploaded?.();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Upload resumes"
      description="Upload one or more resume files. Optional fields apply to single uploads."
      size="lg"
      footer={
        <>
          <Button variant="outline" onClick={handleClose} disabled={submitting}>
            {results ? "Close" : "Cancel"}
          </Button>
          {!results && (
            <Button onClick={submit} loading={submitting}>
              Upload {files.length > 0 ? `(${files.length})` : ""}
            </Button>
          )}
        </>
      }
    >
      {!results ? (
        <div className="space-y-4">
          <div
            onClick={() => fileInput.current?.click()}
            className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center transition hover:border-indigo-300 hover:bg-indigo-50/40"
          >
            <Upload className="h-6 w-6 text-slate-400" />
            <p className="text-sm text-slate-600">
              Click to choose files (PDF / DOC / DOCX)
            </p>
            <p className="text-xs text-slate-400">
              {files.length > 0
                ? `${files.length} file(s) selected`
                : "Multiple files allowed"}
            </p>
            <input
              ref={fileInput}
              type="file"
              multiple
              accept=".pdf,.doc,.docx,application/pdf"
              className="hidden"
              onChange={(e) =>
                setFiles(e.target.files ? Array.from(e.target.files) : [])
              }
            />
          </div>

          {files.length > 0 && (
            <ul className="space-y-1">
              {files.map((f) => (
                <li
                  key={f.name}
                  className="flex items-center gap-2 rounded-md bg-slate-50 px-3 py-1.5 text-xs text-slate-600"
                >
                  <FileCheck2 className="h-4 w-4 text-slate-400" />
                  {f.name}
                </li>
              ))}
            </ul>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              label="Email (optional)"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input
              label="Full name (optional)"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Source (optional)
              </label>
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
                className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              >
                <option value="">—</option>
                {SOURCES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <Input
              label="Source detail (optional)"
              value={sourceDetail}
              onChange={(e) => setSourceDetail(e.target.value)}
            />
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {results.length === 0 && (
            <p className="text-sm text-slate-500">No results returned.</p>
          )}
          {results.map((r, i) => (
            <div
              key={`${r.filename}-${i}`}
              className={cn(
                "rounded-lg border p-3",
                r.error
                  ? "border-red-200 bg-red-50"
                  : "border-emerald-200 bg-emerald-50",
              )}
            >
              <div className="flex items-center gap-2">
                {r.error ? (
                  <FileX2 className="h-4 w-4 text-red-600" />
                ) : (
                  <FileCheck2 className="h-4 w-4 text-emerald-600" />
                )}
                <span className="text-sm font-medium text-slate-700">
                  {r.filename}
                </span>
                {r.is_new !== undefined && !r.error && (
                  <span className="ml-auto text-xs text-slate-500">
                    {r.is_new ? "New candidate" : "Existing candidate"}
                  </span>
                )}
              </div>
              {r.error && (
                <p className="mt-1 text-xs text-red-700">
                  {r.error}
                  {r.message ? ` — ${r.message}` : ""}
                </p>
              )}
              {r.ai_summary && (
                <p className="mt-1 line-clamp-2 text-xs text-slate-600">
                  {r.ai_summary}
                </p>
              )}
              {r.skills && r.skills.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {r.skills.slice(0, 8).map((s) => (
                    <span
                      key={s}
                      className="rounded bg-white px-1.5 py-0.5 text-[11px] text-slate-600 ring-1 ring-slate-200"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {submitting && !results && (
        <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Parsing resumes with AI…
        </div>
      )}
    </Modal>
  );
}
