import { redirect } from "next/navigation";

// No dashboard content of its own (yet — see plan: Phase 5 stats) — the
// nav bar (see components/Nav.tsx) is the way to get around the app, so
// landing here just takes you straight to your library.
export default function Home() {
  redirect("/gallery");
}
