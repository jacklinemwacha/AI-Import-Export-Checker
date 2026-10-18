import { Link, useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useSession, ROLE_LABEL } from "@/lib/session";

export function AppShell({ children }: { children: ReactNode }) {
  const { settings, user, setSettings } = useSession();
  const navigate = useNavigate();
  return (
    <div className="min-h-screen">
      <header className="border-b-2 border-primary bg-card">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-5 py-3">
          <Link to="/shipments" className="flex items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-sm bg-primary font-mono text-sm font-bold text-primary-foreground">IE</span>
            <span className="font-semibold tracking-tight">Import-Export Checker</span>
          </Link>
          {settings && (
            <div className="flex items-center gap-3 text-sm">
              <span className={`stamp ${settings.mode === "demo" ? "text-accent" : "text-success"}`}>
                {settings.mode === "demo" ? "Demo data" : "Live API"}
              </span>
              <span className="hidden text-muted-foreground sm:inline">
                {settings.email} · {user ? ROLE_LABEL[user.role] : "user"}
              </span>
              <button
                className="rounded-sm border px-3 py-1.5 hover:bg-secondary"
                onClick={() => {
                  setSettings(null);
                  navigate({ to: "/" });
                }}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-8">{children}</main>
    </div>
  );
}

export function StatusStamp({ status }: { status: string }) {
  const tone =
    status === "approved" ? "text-success" : status === "documents_uploaded" ? "text-accent" : "text-muted-foreground";
  return <span className={`stamp ${tone}`}>{status.replace(/_/g, " ")}</span>;
}
