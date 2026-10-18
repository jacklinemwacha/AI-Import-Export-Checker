import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { AppShell, StatusStamp } from "@/components/AppShell";
import { canCreate, createShipment, listShipments, DOC_TYPES } from "@/lib/api";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/shipments/")({
  head: () => ({
    meta: [
      { title: "Shipments — Import-Export Checker" },
      { name: "description", content: "All shipment cases you can see, with document status." },
      { property: "og:title", content: "Shipments — Import-Export Checker" },
      { property: "og:description", content: "All shipment cases you can see, with document status." },
    ],
  }),
  component: Shipments,
});

function Shipments() {
  const { settings, ready, user } = useSession();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [reference, setReference] = useState("");

  useEffect(() => {
    if (ready && !settings) navigate({ to: "/" });
  }, [ready, settings, navigate]);

  const q = useQuery({
    queryKey: ["shipments", settings],
    queryFn: () => listShipments(settings!),
    enabled: !!settings,
  });
  const create = useMutation({
    mutationFn: (ref: string) => createShipment(settings!, ref),
    onSuccess: (sh) => {
      qc.invalidateQueries({ queryKey: ["shipments"] });
      navigate({ to: "/shipments/$id", params: { id: sh.id } });
    },
  });

  if (!settings) return <AppShell>{null}</AppShell>;
  const allowed = user ? canCreate(user.role) : true;

  return (
    <AppShell>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Shipments</h1>
          <p className="text-muted-foreground">Each case needs three documents before it can be checked.</p>
        </div>
        {allowed && (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (reference.trim()) create.mutate(reference.trim());
            }}
          >
            <input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="SHP-0005"
              className="w-36 rounded-sm border bg-card px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              disabled={create.isPending}
              className="rounded-sm bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {create.isPending ? "Creating…" : "New shipment"}
            </button>
          </form>
        )}
      </div>
      {create.error && <ErrorBox error={create.error} />}

      <div className="mt-6 overflow-hidden rounded-sm border-2 bg-card">
        {q.isLoading && <p className="p-6 text-muted-foreground">Loading shipments…</p>}
        {q.error && <div className="p-4"><ErrorBox error={q.error} /></div>}
        {q.data && q.data.length === 0 && (
          <p className="p-10 text-center text-muted-foreground">
            No shipments yet.{allowed ? " Create one with a reference above." : ""}
          </p>
        )}
        {q.data && q.data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left font-mono text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Reference</th>
                <th className="px-4 py-3">Documents</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((s) => (
                <tr key={s.id} className="border-t hover:bg-muted">
                  <td className="px-4 py-3">
                    <Link to="/shipments/$id" params={{ id: s.id }} className="font-mono font-semibold underline-offset-4 hover:underline">
                      {s.reference}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{s.documents ? `${s.documents.length} / ${DOC_TYPES.length}` : "—"}</td>
                  <td className="px-4 py-3"><StatusStamp status={s.status} /></td>
                  <td className="px-4 py-3 text-muted-foreground">{s.created_at ? new Date(s.created_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </AppShell>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const e = error as { status?: number; message?: string };
  return (
    <div className="mt-4 rounded-sm border-2 border-destructive bg-card p-3 text-sm text-destructive">
      {e.status ? <span className="mr-2 font-mono font-bold">{e.status}</span> : null}
      {e.message || "Something went wrong"}
    </div>
  );
}
