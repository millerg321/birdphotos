"use client";

import { useState } from "react";
import { wikipediaSearchUrl } from "@/lib/wikipedia";
import { LocationAutocomplete } from "@/components/LocationAutocomplete";

interface Candidate {
  common_name: string;
  scientific_name: string | null;
  confidence: number;
}

interface IdentifyResult {
  candidates: Candidate[];
  notes: string | null;
}

const MAX_DIMENSION = 1600;
const JPEG_QUALITY = 0.85;

// Resizes/re-encodes client-side before upload for two reasons: it
// keeps the request comfortably under Vercel's body size limit without
// needing R2 staging (see plan: ephemeral photo identification — this
// path never touches R2 at all), and it guarantees the bytes are a
// JPEG the server-side magic-byte check (app/api/identify/route.ts)
// will actually accept, regardless of the source file's original type.
function resizeToJpeg(file: File): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, MAX_DIMENSION / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Canvas not supported"));
        return;
      }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("Could not encode photo"))),
        "image/jpeg",
        JPEG_QUALITY,
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not read photo"));
    };
    img.src = url;
  });
}

export function IdentifyForm({ knownLocations }: { knownLocations: string[] }) {
  const [location, setLocation] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [result, setResult] = useState<IdentifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) {
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    setPreviewUrl(URL.createObjectURL(file));

    try {
      const jpeg = await resizeToJpeg(file);
      const formData = new FormData();
      formData.append("file", jpeg, "photo.jpg");
      if (location.trim() !== "") {
        formData.append("location", location.trim());
      }

      const response = await fetch("/api/identify", { method: "POST", body: formData });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.error ?? "Identification failed");
      }
      setResult(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Identification failed");
    }
    setSubmitting(false);
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <label htmlFor="location" className="mb-1 block text-sm text-zinc-500">
          Location (optional)
        </label>
        <LocationAutocomplete
          id="location"
          value={location}
          onValueChange={setLocation}
          onSelect={setLocation}
          options={knownLocations}
          placeholder="e.g. Borneo, or South Africa"
          disabled={submitting}
          maxLength={200}
          className="w-full rounded-md border border-zinc-300 bg-transparent px-3 py-2 text-sm text-black placeholder:text-zinc-400 dark:border-zinc-700 dark:text-zinc-50"
        />
        <p className="mt-1 text-xs text-zinc-500">
          Roughly where the photo was taken — a country or region is
          enough. Without it, the AI tends to default toward whichever
          similar-looking species is most common worldwide, so this
          helps it rule out birds that don&apos;t actually occur there.
        </p>
      </div>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          if (!submitting) setIsDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (submitting) return;
          const dropped = Array.from(e.dataTransfer.files).find((f) =>
            f.type.startsWith("image/"),
          );
          handleFile(dropped);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center text-sm transition-colors ${
          isDragging
            ? "border-blue-500 bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400"
            : "border-zinc-300 bg-zinc-100 text-zinc-500 hover:bg-zinc-200 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        }`}
      >
        <span>
          {submitting
            ? "Identifying…"
            : isDragging
              ? "Drop to identify"
              : "Choose, take, or drag and drop a photo"}
        </span>
        <input
          type="file"
          accept="image/*"
          disabled={submitting}
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </label>

      {previewUrl && (
        // eslint-disable-next-line @next/next/no-img-element -- local object URL, not an R2 asset
        <img
          src={previewUrl}
          alt=""
          className="max-h-80 w-full rounded-md object-contain"
        />
      )}

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {result && result.candidates.length === 0 && (
        <p className="text-sm text-zinc-500">No bird could be identified in this photo.</p>
      )}

      {result && result.candidates.length > 0 && (
        <ul className="space-y-2">
          {result.candidates.map((candidate) => (
            <li
              key={candidate.common_name}
              className="flex items-center justify-between gap-3 rounded-md bg-zinc-100 px-3 py-2 text-sm dark:bg-zinc-900"
            >
              <span className="text-black dark:text-zinc-50">
                {candidate.common_name}
                {candidate.scientific_name && (
                  <span className="text-zinc-500 italic"> — {candidate.scientific_name}</span>
                )}{" "}
                <a
                  href={wikipediaSearchUrl(candidate.scientific_name ?? candidate.common_name)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                >
                  Wikipedia ↗
                </a>
              </span>
              <span className="text-zinc-500">{Math.round(candidate.confidence * 100)}%</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
