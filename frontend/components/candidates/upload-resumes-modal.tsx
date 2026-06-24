"use client";

import { useRef, useState } from "react";
import { FileCheck2, FileX2, Loader2, UploadCloud, X } from "lucide-react";
import { toast } from "sonner";

import { apiUpload } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { UploadResponse, UploadResultItem } from "@/lib/types";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const SOURCES = ["LINKEDIN", "NAUKRI", "EMAIL", "REFERRAL", "OTHER"];

export function UploadResumesModal({
  open,
  onOpenChange,
  onUploaded,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUploaded?: () => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [source, setSource] = useState("EMAIL");
  const [sourceDetail, setSourceDetail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState<UploadResultItem[] | null>(null);

  const reset = () => {
    setFiles([]);
    setEmail("");
    setFullName("");
    setSource("EMAIL");
    setSourceDetail("");
    setResults(null);
  };

  const close = (v: boolean) => {
    if (submitting) return;
    if (!v) reset();
    onOpenChange(v);
  };

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
  };

  const submit = async () => {
    if (!files.length) return toast.error("Select at least one resume file");
    setSubmitting(true);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      if (files.length === 1 && email.trim()) fd.append("email", email.trim());
      if (files.length === 1 && fullName.trim()) fd.append("full_name", fullName.trim());
      fd.append("source", source);
      if (sourceDetail.trim()) fd.append("source_detail", sourceDetail.trim());
      const res = await apiUpload<UploadResponse>("/candidates", fd);
      setResults(res.results ?? []);
      const ok = (res.results ?? []).filter((r) => !r.error).length;
      const fail = (res.results ?? []).filter((r) => r.error).length;
      if (ok) toast.success(`${ok} resume${ok > 1 ? "s" : ""} processed`);
      if (fail) toast.error(`${fail} resume${fail > 1 ? "s" : ""} failed`);
      onUploaded?.();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload resumes</DialogTitle>
          <DialogDescription>
            The resume-intake agent extracts skills and profile data. Optional
            fields apply to single uploads.
          </DialogDescription>
        </DialogHeader>

        {!results ? (
          <div className="space-y-4">
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileInput.current?.click()}
              onKeyDown={(e) => e.key === "Enter" && fileInput.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                addFiles(e.dataTransfer.files);
              }}
              className="border-input hover:border-primary/50 hover:bg-accent/40 flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors"
            >
              <UploadCloud className="text-muted-foreground size-7" />
              <p className="text-sm font-medium">Click or drop files here</p>
              <p className="text-muted-foreground text-xs">PDF, DOC, DOCX · multiple allowed</p>
              <input
                ref={fileInput}
                type="file"
                multiple
                accept=".pdf,.doc,.docx"
                className="hidden"
                onChange={(e) => addFiles(e.target.files)}
              />
            </div>

            {files.length > 0 && (
              <div className="max-h-32 space-y-1.5 overflow-y-auto">
                {files.map((f, i) => (
                  <div
                    key={i}
                    className="bg-muted/50 flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm"
                  >
                    <FileCheck2 className="text-muted-foreground size-4 shrink-0" />
                    <span className="truncate">{f.name}</span>
                    <button
                      onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}
                      className="text-muted-foreground hover:text-foreground ml-auto"
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Source</Label>
                <Select value={source} onValueChange={setSource}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s.charAt(0) + s.slice(1).toLowerCase()}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Source detail</Label>
                <Input
                  value={sourceDetail}
                  onChange={(e) => setSourceDetail(e.target.value)}
                  placeholder="e.g. campaign name"
                />
              </div>
            </div>
            {files.length === 1 && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Email (optional)</Label>
                  <Input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
                </div>
                <div className="space-y-1.5">
                  <Label>Full name (optional)</Label>
                  <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="max-h-72 space-y-2 overflow-y-auto">
            {results.map((r, i) => (
              <div
                key={i}
                className={cn(
                  "flex items-start gap-2.5 rounded-lg border p-3 text-sm",
                  r.error ? "border-destructive/30 bg-destructive/5" : "bg-muted/40",
                )}
              >
                {r.error ? (
                  <FileX2 className="text-destructive mt-0.5 size-4 shrink-0" />
                ) : (
                  <FileCheck2 className="mt-0.5 size-4 shrink-0 text-emerald-500" />
                )}
                <div className="min-w-0">
                  <p className="truncate font-medium">{r.filename}</p>
                  {r.error ? (
                    <p className="text-destructive text-xs">{r.message || r.error}</p>
                  ) : (
                    <p className="text-muted-foreground text-xs">
                      {r.is_new ? "New candidate" : "Updated"} ·{" "}
                      {r.skills?.length ?? 0} skills extracted
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)} disabled={submitting}>
            {results ? "Close" : "Cancel"}
          </Button>
          {!results && (
            <Button onClick={submit} disabled={submitting || !files.length}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Upload{files.length ? ` (${files.length})` : ""}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
