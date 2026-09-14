import { IdentifyForm } from "./IdentifyForm";

export default function IdentifyPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col gap-6 bg-zinc-50 px-6 py-10 dark:bg-black">
      <div>
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          Identify a bird
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Upload a photo and get an AI species suggestion. Nothing you upload
          here is saved.
        </p>
      </div>
      <IdentifyForm />
    </main>
  );
}
