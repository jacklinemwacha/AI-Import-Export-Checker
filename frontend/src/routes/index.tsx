import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { DEMO_USERS } from "@/lib/api";
import { useSession, ROLE_LABEL } from "@/lib/session";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Sign in — Import-Export Checker" },
      { name: "description", content: "Sign in to check shipment documents before customs clearance." },
      { property: "og:title", content: "Sign in — Import-Export Checker" },
      { property: "og:description", content: "Sign in to check shipment documents before customs clearance." },
    ],
  }),
  component: SignIn,
});

function SignIn() {
  const { settings, ready, setSettings } = useSession();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [baseUrl, setBaseUrl] = useState("http://localhost:8000");

  useEffect(() => {
    if (ready && settings) navigate({ to: "/shipments" });
  }, [ready, settings, navigate]);

  return (
    <AppShell>
      <div className="mx-auto max-w-xl">
        <p className="stamp text-accent">Customs pre-check</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">Who is signing in?</h1>
        <p className="mt-2 text-muted-foreground">Pick a demo account. Each role sees and can do different things.</p>

        <div className="mt-6 flex gap-2 rounded-sm border bg-card p-1 text-sm">
          {(["demo", "live"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`flex-1 rounded-sm px-3 py-2 ${mode === m ? "bg-primary text-primary-foreground" : "hover:bg-secondary"}`}
            >
              {m === "demo" ? "Demo data (in this browser)" : "Connect to my API"}
            </button>
          ))}
        </div>

        {mode === "live" && (
          <label className="mt-4 block text-sm">
            <span className="font-medium">API address</span>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="mt-1 w-full rounded-sm border bg-card px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              Needs DEMO_MODE=true and CORS allowing this site on the server.
            </span>
          </label>
        )}

        <ul className="mt-6 grid gap-3 sm:grid-cols-2">
          {DEMO_USERS.map((u) => (
            <li key={u.email}>
              <button
                onClick={() => setSettings({ mode, baseUrl, email: u.email })}
                className="w-full rounded-sm border-2 bg-card p-4 text-left transition hover:-translate-y-0.5 hover:border-accent"
              >
                <span className="block font-semibold">{ROLE_LABEL[u.role]}</span>
                <span className="block font-mono text-xs text-muted-foreground">{u.email}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </AppShell>
  );
}
