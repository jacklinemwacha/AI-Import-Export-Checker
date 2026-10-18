// Client for the AI Import-Export Checker FastAPI backend.
// "demo" mode keeps data in the browser with the same rules as the backend.

export type Role = "importer" | "clearing_agent" | "reviewer" | "admin";
export type DocType = "commercial_invoice" | "packing_list" | "bill_of_lading";
export const DOC_TYPES: { type: DocType; label: string }[] = [
  { type: "commercial_invoice", label: "Commercial invoice" },
  { type: "packing_list", label: "Packing list" },
  { type: "bill_of_lading", label: "Bill of lading" },
];

export const DEMO_USERS: { email: string; name: string; role: Role }[] = [
  { email: "importer@demo.test", name: "Demo Importer", role: "importer" },
  { email: "agent@demo.test", name: "Demo Clearing Agent", role: "clearing_agent" },
  { email: "reviewer@demo.test", name: "Demo Reviewer", role: "reviewer" },
  { email: "admin@demo.test", name: "Demo Admin", role: "admin" },
];

export type ShipmentDocument = {
  id: string;
  doc_type: DocType;
  original_filename?: string;
  size_bytes?: number;
  sha256?: string;
  uploaded_at?: string;
};
export type Shipment = {
  id: string;
  reference: string;
  status: string;
  owner_id?: string;
  created_at?: string;
  updated_at?: string;
  documents?: ShipmentDocument[];
};

export type Settings = { mode: "demo" | "live"; baseUrl: string; email: string };
const SETTINGS_KEY = "iec.settings";

export function loadSettings(): Settings | null {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? (JSON.parse(raw) as Settings) : null;
  } catch {
    return null;
  }
}
export function saveSettings(s: Settings | null) {
  if (s) localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  else localStorage.removeItem(SETTINGS_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function canCreate(role: Role) {
  return role === "importer" || role === "clearing_agent";
}

// ---------- live ----------
async function live<T>(s: Settings, path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(s.baseUrl.replace(/\/$/, "") + path, {
      ...init,
      headers: { "X-Demo-User": s.email, ...(init.headers || {}) },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is it running, and is CORS enabled?");
  }
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : text;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}
function safeJson(t: string) {
  try { return JSON.parse(t); } catch { return t; }
}

// ---------- demo ----------
const DEMO_KEY = "iec.demo.shipments";
type DemoShipment = Shipment & { owner_email: string };
function demoAll(): DemoShipment[] {
  try { return JSON.parse(localStorage.getItem(DEMO_KEY) || "[]"); } catch { return []; }
}
function demoSave(list: DemoShipment[]) {
  localStorage.setItem(DEMO_KEY, JSON.stringify(list));
}
function demoUser(email: string) {
  const u = DEMO_USERS.find((x) => x.email === email);
  if (!u) throw new ApiError(401, "Unknown user");
  return u;
}
function visible(email: string, sh: DemoShipment) {
  const u = demoUser(email);
  return u.role === "reviewer" || u.role === "admin" || sh.owner_email === email;
}
const now = () => new Date().toISOString();
const uid = () => crypto.randomUUID();
function strip({ owner_email: _o, ...rest }: DemoShipment): Shipment {
  return rest;
}

export async function listShipments(s: Settings): Promise<Shipment[]> {
  if (s.mode === "live") return live<Shipment[]>(s, "/shipments");
  demoUser(s.email);
  return demoAll().filter((x) => visible(s.email, x)).map(strip);
}

export async function getShipment(s: Settings, id: string): Promise<Shipment> {
  if (s.mode === "live") return live<Shipment>(s, `/shipments/${id}`);
  const sh = demoAll().find((x) => x.id === id);
  if (!sh || !visible(s.email, sh)) throw new ApiError(404, "Shipment not found");
  return strip(sh);
}

export async function createShipment(s: Settings, reference: string): Promise<Shipment> {
  if (s.mode === "live")
    return live<Shipment>(s, "/shipments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reference }),
    });
  const u = demoUser(s.email);
  if (!canCreate(u.role)) throw new ApiError(403, "Your role cannot create shipments");
  const sh: DemoShipment = {
    id: uid(), reference, status: "created", owner_email: u.email,
    created_at: now(), updated_at: now(), documents: [],
  };
  demoSave([sh, ...demoAll()]);
  return strip(sh);
}

const ALLOWED = ["application/pdf", "image/png", "image/jpeg"];
export async function uploadDocument(s: Settings, id: string, docType: DocType, file: File): Promise<unknown> {
  if (s.mode === "live") {
    const fd = new FormData();
    fd.append("doc_type", docType);
    fd.append("file", file);
    return live(s, `/shipments/${id}/documents`, { method: "POST", body: fd });
  }
  const list = demoAll();
  const sh = list.find((x) => x.id === id);
  if (!sh || !visible(s.email, sh)) throw new ApiError(404, "Shipment not found");
  if (!canCreate(demoUser(s.email).role)) throw new ApiError(403, "Your role cannot upload documents");
  if (sh.status === "approved") throw new ApiError(409, "Approved cases cannot change");
  if (!ALLOWED.includes(file.type)) throw new ApiError(400, "Only PDF, PNG or JPEG files are allowed");
  if (file.size > 10 * 1024 * 1024) throw new ApiError(400, "File is larger than 10 MB");
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  const sha = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  const docs = (sh.documents || []).filter((d) => d.doc_type !== docType);
  docs.push({ id: uid(), doc_type: docType, original_filename: file.name, size_bytes: file.size, sha256: sha, uploaded_at: now() });
  sh.documents = docs;
  sh.status = DOC_TYPES.every((t) => docs.some((d) => d.doc_type === t.type)) ? "documents_uploaded" : "created";
  sh.updated_at = now();
  demoSave(list);
  return docs[docs.length - 1];
}
