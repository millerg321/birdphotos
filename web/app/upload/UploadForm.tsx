"use client";

import { useState } from "react";
import { getUploadUrlAction, processUploadsAction, rescanAction } from "@/lib/actions/upload";

interface FileStatus {
  name: string;
  state: "pending" | "uploading" | "processing" | "done" | "error";
  error?: string;
}

export function UploadForm() {
  const [statuses, setStatuses] = useState<FileStatus[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [rescanning, setRescanning] = useState(false);
  const [rescanResult, setRescanResult] = useState<string | null>(null);

  async function handleRescan() {
    setRescanning(true);
    setRescanResult(null);
    try {
      const result = await rescanAction();
      setRescanResult(
        `Scored ${result.scored}, ${result.groups} burst group(s) total, ` +
          `${result.classified} newly classified`,
      );
    } catch (err) {
      setRescanResult(err instanceof Error ? err.message : "Rescan failed");
    }
    setRescanning(false);
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) {
      return;
    }
    const fileList = Array.from(files);
    setSubmitting(true);
    setSummary(null);
    setStatuses(fileList.map((f) => ({ name: f.name, state: "pending" })));

    const uploadedKeys: string[] = [];

    // Sequential rather than Promise.all — keeps status updates simple to
    // follow in the UI and avoids hammering R2 with a large simultaneous
    // batch when someone selects dozens of files at once.
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      setStatuses((prev) =>
        prev.map((s, idx) => (idx === i ? { ...s, state: "uploading" } : s)),
      );
      try {
        const { r2Key, uploadUrl } = await getUploadUrlAction(file.name);
        const putResponse = await fetch(uploadUrl, {
          method: "PUT",
          headers: { "Content-Type": "application/octet-stream" },
          body: file,
        });
        if (!putResponse.ok) {
          throw new Error(`Upload failed: ${putResponse.status}`);
        }
        uploadedKeys.push(r2Key);
        setStatuses((prev) =>
          prev.map((s, idx) => (idx === i ? { ...s, state: "processing" } : s)),
        );
      } catch (err) {
        setStatuses((prev) =>
          prev.map((s, idx) =>
            idx === i
              ? { ...s, state: "error", error: err instanceof Error ? err.message : "Upload failed" }
              : s,
          ),
        );
      }
    }

    if (uploadedKeys.length > 0) {
      try {
        const result = await processUploadsAction(uploadedKeys);
        const errorsByKey = new Map(result.errors.map((e) => [e.r2Key, e.error]));
        // Map processing results back onto the uploaded (non-error) files,
        // in the same order they were sent to processUploadsAction.
        let uploadedIdx = 0;
        setStatuses((prev) =>
          prev.map((s) => {
            if (s.state !== "processing") {
              return s;
            }
            const key = uploadedKeys[uploadedIdx];
            uploadedIdx += 1;
            const error = errorsByKey.get(key);
            return error ? { ...s, state: "error", error } : { ...s, state: "done" };
          }),
        );
        setSummary(
          `${result.imported} photo${result.imported === 1 ? "" : "s"} imported` +
            (result.errors.length > 0 ? `, ${result.errors.length} failed` : ""),
        );
      } catch (err) {
        setStatuses((prev) =>
          prev.map((s) =>
            s.state === "processing"
              ? { ...s, state: "error", error: err instanceof Error ? err.message : "Processing failed" }
              : s,
          ),
        );
        setSummary("Processing failed");
      }
    }

    setSubmitting(false);
  }

  return (
    <div className="flex flex-col gap-4">
      <label className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-zinc-300 bg-zinc-100 px-6 py-10 text-center text-sm text-zinc-500 hover:bg-zinc-200 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800">
        <span>Click to choose one or more photos</span>
        <input
          type="file"
          multiple
          accept="image/*"
          disabled={submitting}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </label>

      {statuses.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {statuses.map((s) => (
            <li key={s.name} className="flex items-center justify-between gap-2">
              <span className="truncate text-black dark:text-zinc-50">{s.name}</span>
              <span
                className={
                  s.state === "error"
                    ? "text-red-600 dark:text-red-400"
                    : s.state === "done"
                      ? "text-green-600 dark:text-green-400"
                      : "text-zinc-500"
                }
              >
                {s.state === "error" ? (s.error ?? "error") : s.state}
              </span>
            </li>
          ))}
        </ul>
      )}

      {summary && (
        <p className="text-sm text-zinc-700 dark:text-zinc-300">{summary}</p>
      )}

      <div className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
        <p className="mb-2 text-xs text-zinc-500">
          Newly uploaded photos aren&apos;t scored, grouped into bursts, or
          run through AI species suggestion until this runs. It rescans the
          whole library, so run it once after a batch rather than after
          each photo.
        </p>
        <button
          type="button"
          onClick={handleRescan}
          disabled={rescanning}
          className="rounded-md bg-zinc-200 px-3 py-1.5 text-sm text-black hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:text-zinc-50 dark:hover:bg-zinc-700"
        >
          {rescanning ? "Scoring, grouping & classifying…" : "Score, group & classify new photos"}
        </button>
        {rescanResult && (
          <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{rescanResult}</p>
        )}
      </div>
    </div>
  );
}
