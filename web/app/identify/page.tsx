import { getKnownLocationNames } from "@/lib/db/queries";
import { IdentifyForm } from "./IdentifyForm";

// Public (see lib/publicPaths.ts) — getKnownLocationNames just returns
// place names already used elsewhere in the library (e.g. "London, UK"),
// not anything sensitive, same reasoning as /gallery's own public data.
export default async function IdentifyPage() {
  const knownLocations = await getKnownLocationNames();

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
      <IdentifyForm knownLocations={knownLocations} />
    </main>
  );
}
