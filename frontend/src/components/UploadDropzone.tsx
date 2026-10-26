import { useRef, useState, type DragEvent } from "react";
import { Alert, Button } from "./ui";

export const MAX_FILES = 20;
export const MAX_MB = 5;

interface Props {
  remaining: number; // candidates left before the per-job limit
  locked: boolean;
  onUpload(files: File[]): Promise<void>;
}

/**
 * Multi-file PDF picker. File names are shown only in validation errors for files
 * that are *not* uploaded; accepted files appear as a count, so no name stays on screen.
 */
export function UploadDropzone({ remaining, locked, onUpload }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);

  const limit = Math.min(MAX_FILES, remaining);

  function choose(list: FileList | null) {
    if (!list) return;
    const ok: File[] = [];
    const bad: string[] = [];
    for (const f of Array.from(list)) {
      if (!f.name.toLowerCase().endsWith(".pdf")) bad.push(`${f.name}: not a PDF`);
      else if (f.size > MAX_MB * 1024 * 1024) bad.push(`${f.name}: larger than ${MAX_MB} MB`);
      else ok.push(f);
    }
    if (ok.length > limit) {
      bad.push(`Only ${limit} more file${limit === 1 ? "" : "s"} can be added; ${ok.length - limit} left out.`);
      ok.length = limit;
    }
    setFiles(ok);
    setProblems(bad);
    setError(null);
  }

  async function upload() {
    setBusy(true);
    setError(null);
    try {
      await onUpload(files);
      setFiles([]);
      setProblems([]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    choose(e.dataTransfer.files);
  };

  if (remaining <= 0) {
    return <Alert tone="info">This job has reached the limit of 50 candidates.</Alert>;
  }

  const sizeMb = files.reduce((s, f) => s + f.size, 0) / (1024 * 1024);

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        role="button"
        tabIndex={0}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-slate-50 hover:border-indigo-400 hover:bg-indigo-50/40"
        }`}
      >
        <svg className="size-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V3m0 0L7.5 7.5M12 3l4.5 4.5M3 15v3.75A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V15" />
        </svg>
        <p className="mt-2 text-sm font-medium text-slate-700">Drop PDF resumes here, or click to choose</p>
        <p className="mt-1 text-xs text-slate-500">
          PDF only · up to {MAX_MB} MB each · up to {limit} files. Files are processed in memory and never stored.
        </p>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => choose(e.target.files)} />
      </div>

      {problems.length > 0 && (
        <Alert tone="warning">
          <p className="font-medium">Some files were left out:</p>
          <ul className="mt-1 list-disc pl-5">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Alert>
      )}
      {error && <Alert>{error}</Alert>}

      {files.length > 0 && (
        <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-700">
            <span className="font-semibold">{files.length}</span> PDF{files.length === 1 ? "" : "s"} ready ({sizeMb.toFixed(1)} MB)
            {!locked && <span className="block text-xs text-slate-500">Tags lock once screening starts; their weights can still change.</span>}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setFiles([])} disabled={busy}>
              Clear
            </Button>
            <Button size="sm" onClick={upload} loading={busy}>
              Screen {files.length} resume{files.length === 1 ? "" : "s"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
