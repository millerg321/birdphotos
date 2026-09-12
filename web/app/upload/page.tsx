import Link from "next/link";
import { UploadForm } from "./UploadForm";

export default function UploadPage() {
  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <Link href="/gallery" className="text-sm text-zinc-500 hover:underline">
        &larr; Back to gallery
      </Link>
      <h1 className="mt-2 mb-6 text-2xl font-semibold text-black dark:text-zinc-50">
        Upload photos
      </h1>
      <div className="max-w-lg">
        <UploadForm />
      </div>
    </main>
  );
}
