/**
 * Casos editoriais — cliente /v1/casos.
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

export type CasoListItem = {
  id: string;
  nome: string;
  periodo?: string | null;
  eixos?: string[];
  resumo?: string | null;
};

export async function fetchCasosList(opts?: { q?: string; limit?: number }) {
  const p = new URLSearchParams();
  if (opts?.q) p.set("q", opts.q);
  p.set("limit", String(opts?.limit ?? 500));
  return getJson<{
    items?: CasoListItem[];
    total?: number;
    source?: string;
    disclaimer?: string;
  }>(`/v1/casos?${p.toString()}`);
}

export async function fetchCasoDetail(id: string) {
  return getJson<{
    ok?: boolean;
    caso?: Record<string, unknown> & {
      id: string;
      nome: string;
      periodo?: string;
      eixos?: string[];
    };
    regs?: Array<Record<string, unknown>>;
    pessoas?: Record<
      string,
      { id: string; nome?: string; partido?: string; cargo_atual?: string }
    >;
    disclaimer?: string;
    source?: string;
  }>(`/v1/casos/${encodeURIComponent(id)}`);
}
