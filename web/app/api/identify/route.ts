import { NextRequest, NextResponse } from "next/server";
import { checkDailyCap, checkIdentifyRateLimit, extractClientIp } from "@/lib/rateLimit";

// Anonymous, unauthenticated by design (see plan: ephemeral photo
// identification) — this is the only Next.js entry point that lets the
// public trigger a real Anthropic API call, so unlike every other
// worker-calling code path in this app (lib/actions/*.ts, all gated by
// requireSession()) it's rate-limited and cost-capped instead.
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;
const JPEG_MAGIC_BYTES = [0xff, 0xd8, 0xff];

function isJpeg(bytes: Uint8Array): boolean {
  return JPEG_MAGIC_BYTES.every((byte, i) => bytes[i] === byte);
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  // Daily cap first — cheapest check, and the real budget backstop
  // since it holds even against an attacker rotating IPs — before the
  // per-IP limiter.
  if (!(await checkDailyCap())) {
    return NextResponse.json(
      { error: "Identify is temporarily unavailable (daily limit reached) — try again tomorrow." },
      { status: 429 },
    );
  }

  const ip = extractClientIp(request.headers.get("x-forwarded-for"));
  if (!(await checkIdentifyRateLimit(ip))) {
    return NextResponse.json(
      { error: "Too many requests — try again in a bit." },
      { status: 429 },
    );
  }

  const formData = await request.formData();
  const file = formData.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No photo provided" }, { status: 400 });
  }
  if (file.size === 0 || file.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json({ error: "Photo is too large" }, { status: 400 });
  }

  const bytes = new Uint8Array(await file.arrayBuffer());
  // Real content sniffing, not the browser-declared Content-Type — this
  // endpoint has no auth backstop the way getUploadUrlAction's presigned
  // R2 PUT does (lib/actions/upload.ts), so client-supplied metadata
  // can't be trusted at all. The identify page always sends a canvas
  // re-encoded JPEG, so this doubles as confirming the client did that.
  if (!isJpeg(bytes)) {
    return NextResponse.json({ error: "Only JPEG photos are supported" }, { status: 400 });
  }

  const workerForm = new FormData();
  workerForm.append("file", new Blob([bytes], { type: "image/jpeg" }), "photo.jpg");

  // Optional — an anonymous visitor may not know or want to share it.
  // Length capping happens worker-side too (app/main.py identify_photo);
  // trimming here just avoids forwarding an empty field when the input
  // was left blank or whitespace-only.
  const location = formData.get("location");
  if (typeof location === "string" && location.trim() !== "") {
    workerForm.append("location_hint", location.trim());
  }

  const response = await fetch(`${process.env.WORKER_BASE_URL}/identify`, {
    method: "POST",
    headers: { "X-Internal-Token": process.env.INTERNAL_API_TOKEN! },
    body: workerForm,
  });

  if (!response.ok) {
    return NextResponse.json({ error: "Identification failed — try again." }, { status: 502 });
  }

  const result = await response.json();
  return NextResponse.json(result);
}
