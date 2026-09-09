/**
 * Pessoas — cliente server-side /v1/pessoas (Fase A API-first).
 * Fallback KB só se a API estiver indisponível.
 */

import "server-only";

export type { PessoaListItem } from "./pessoas-types";
import type { PessoaListItem } from "./pessoas-types";

export type PessoaDetail = {
  ok?: boolean;
  pessoa: Record<string, unknown> & { id: string; nome: string; tipo?: string };
  rels: Array<Record<string, unknown>>;
  regs: Array<Record<string, unknown>>;
  casos: Record<string, { id: string; nome: string }>;
  labels: Record<string, string>;
  fontes: string[];
  graphNodes: Array<{ id: string; nome: string; tipo?: string }>;
  graphEdges: Array<Record<string, unknown>>;
  disclaimer?: string;
  source?: string;
};

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

export async function fetchPessoasList(opts: {
  q?: string;
  no_poder?: string;
  escopo?: string;
  uf?: string;
  limit?: number;
}): Promise<{ items: PessoaListItem[]; total: number; source: string } | null> {
  const p = new URLSearchParams();
  if (opts.q) p.set("q", opts.q);
  if (opts.no_poder) p.set("no_poder", opts.no_poder);
  if (opts.escopo) p.set("escopo", opts.escopo);
  if (opts.uf) p.set("uf", opts.uf.toUpperCase());
  p.set("limit", String(opts.limit ?? 2000));
  const data = await getJson<{
    items?: PessoaListItem[];
    total?: number;
    source?: string;
  }>(`/v1/pessoas?${p.toString()}`);
  if (!data?.items) return null;
  return {
    items: data.items,
    total: data.total ?? data.items.length,
    source: data.source || "api",
  };
}

export async function fetchPessoaDetail(
  id: string
): Promise<PessoaDetail | null> {
  return getJson<PessoaDetail>(`/v1/pessoas/${encodeURIComponent(id)}`);
}
