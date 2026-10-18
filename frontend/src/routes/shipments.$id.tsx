import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { AppShell, StatusStamp } from "@/components/AppShell";
import { canCreate, getShipment, uploadDocument, DOC_TYPES, type DocType, type ShipmentDocument } from "@/lib/api";
import { useSession } from "@/lib/session";
import { ErrorBox } from "./shipments.index";

export const Route = createFileRoute("/shipments/$id")({
  head: () => ({
    meta: [
      { title: "Shipment case — Import-Export Checker" },
      { name: "description", content: "Upload and review the documents for one shipment." },
      { property: "og:title", content: "Shipment case — Import-Export Checker" },
      { property: "og:description", content: "Upload and review the documents for one shipment." },
    ],
  }),
  component: ShipmentDetail,
});

function ShipmentDetail() {
  const { id } = Route.useParams();
  const { settings, ready, user } = useSession();
  const navigate = useNavigate();

  useEffect(() => {
    if (ready && !settings) navigate({ to: "/" });
  }, [ready, settings, navigate]);

  const q = useQuery({
    queryKey: ["shipment", id, settings],
    queryFn: () => getShipment(settings!, id),
    enabled: !!settings,
    retry: false,
  });

  if (!settings) return <AppShell>{null}</AppShell>;
  const canUpload = user ? canCreate(user.role) : true;

  return (
    <AppShell>
      <Link to="/shipments" className="text-sm text-muted-foreground hover:text-foreground">← All shipments</Link>
      {q.isLoading && <p className="mt-6 text-muted-foreground">Loading…</p>}
      {q.error && <ErrorBox error={q.error} />}
      {q.data && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <h1 className="font-mono text-3xl font-semibold">{q.data.reference}</h1>
            <StatusStamp status={q.data.status} />
          </div>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{q.data.id}</p>

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {DOC_TYPES.map((t) => (
              <DocSlot
                key={t.type}
                shipmentId={id}
                docType={t.type}
                label={t.label}
                doc={q.data!.documents?.find((d) => d.doc_type === t.type)}
                canUpload={canUpload && q.data!.status !== "approved"}
              />
            ))}
          </div>
          {!canUpload && (
            <p className="mt-4 text-sm text-muted-foreground">Your role can view this case but not upload documents.</p>
          )}
        </>
      )}
    </AppShell>
  );
}

function DocSlot({
  shipmentId, docType, label, doc, canUpload,
}: {
  shipmentId: string; docType: DocType; label: string;
  doc: ShipmentDocument | undefined;
  canUpload: boolean;
}) {
  const { settings } = useSession();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const up = useMutation({
    mutationFn: (f: File) => uploadDocument(settings!, shipmentId, docType, f),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shipment", shipmentId] });
      qc.invalidateQueries({ queryKey: ["shipments"] });
    },
  });

  return (
    <div className={`flex flex-col rounded-sm border-2 bg-card p-4 ${doc ? "border-success" : "border-dashed"}`}>
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">{label}</h2>
        <span className={`stamp ${doc ? "text-success" : "text-muted-foreground"}`}>{doc ? "received" : "missing"}</span>
      </div>
      <div className="mt-3 flex-1 text-sm">
        {doc ? (
          <>
            <p className="truncate font-mono">{doc.original_filename || "Uploaded file"}</p>
            {doc.size_bytes != null && <p className="text-muted-foreground">{(doc.size_bytes / 1024).toFixed(0)} KB</p>}
          </>
        ) : (
          <p className="text-muted-foreground">PDF, PNG or JPEG, up to 10 MB.</p>
        )}
      </div>
      {canUpload && (
        <>
          <input
            ref={input}
            type="file"
            accept="application/pdf,image/png,image/jpeg"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) up.mutate(f);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => input.current?.click()}
            disabled={up.isPending}
            className="mt-4 rounded-sm border px-3 py-2 text-sm font-medium hover:bg-secondary disabled:opacity-50"
          >
            {up.isPending ? "Uploading…" : doc ? "Replace file" : "Upload file"}
          </button>
        </>
      )}
      {up.error && <ErrorBox error={up.error} />}
    </div>
  );
}
