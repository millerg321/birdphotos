import { S3Client, GetObjectCommand, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const client = new S3Client({
  endpoint: `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  region: "auto",
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY_ID!,
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY!,
  },
});

const ONE_HOUR_SECONDS = 60 * 60;

// The bucket is private (not public) — every image URL rendered in the
// browser is a short-lived presigned GET, generated server-side.
export function getSignedImageUrl(key: string): Promise<string> {
  const command = new GetObjectCommand({
    Bucket: process.env.R2_BUCKET,
    Key: key,
  });
  return getSignedUrl(client, command, { expiresIn: ONE_HOUR_SECONDS });
}

const FIFTEEN_MINUTES_SECONDS = 15 * 60;

// Manual upload (see plan): the browser PUTs the file directly to this
// URL, bypassing our server entirely — Vercel's serverless functions
// have a hard 4.5MB request body limit that most real bird photos
// exceed, so the bytes can never pass through a Next.js route/action.
export function getSignedUploadUrl(key: string, contentType: string): Promise<string> {
  const command = new PutObjectCommand({
    Bucket: process.env.R2_BUCKET,
    Key: key,
    ContentType: contentType,
  });
  return getSignedUrl(client, command, { expiresIn: FIFTEEN_MINUTES_SECONDS });
}
