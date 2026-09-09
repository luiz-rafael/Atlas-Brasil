/**
 * Dinheiro — categorias via /v1/dinheiro/{tab}.
 */

import "server-only";

function apiBase(): string {
  return (
    process.env.ATLAS_API_URL ||
    process.env.NEXT_PUBLIC_ATLAS_API_URL ||
    "http://localhost:8001"
  ).replace(/\/$/, "");
}

async function getJson<T>(pathQs: string): Promise<T | null> {
  try {
    const res = await fetch(`${apiBase()}${pathQs}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function fetchDinheiroResumo() {
  return getJson<{
    counts?: Record<string, number>;
    disclaimer?: string;
    note?: string;
  }>("/v1/dinheiro");
}

export async function fetchDinheiroTab(
  tab: string,
  opts?: { caso_id?: string; uf?: string; q?: string; limit?: number }
) {
  const p = new URLSearchParams();
  if (opts?.caso_id) p.set("caso_id", opts.caso_id);
  if (opts?.uf) p.set("uf", opts.uf.toUpperCase());
  if (opts?.q) p.set("q", opts.q);
  p.set("limit", String(opts?.limit ?? 100));
  return getJson<{
    tab?: string;
    items?: Array<Record<string, unknown>>;
    total?: number;
    counts?: Record<string, number>;
    disclaimer?: string;
    filters?: { uf?: string | null; q?: string | null };
  }>(`/v1/dinheiro/${encodeURIComponent(tab)}?${p.toString()}`);
}
