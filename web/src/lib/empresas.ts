/**
 * Empresas — cliente API /v1/empresas.
 */

import "server-only";

export type EmpresaListItem = {
  company_id: string;
  razao_social?: string | null;
  nome_fantasia?: string | null;
  cnpj?: string | null;
  uf?: string | null;
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

export async function fetchEmpresasList(opts?: {
  q?: string;
  limit?: number;
}): Promise<{ items: EmpresaListItem[]; total: number; source: string } | null> {
  const p = new URLSearchParams();
  if (opts?.q) p.set("q", opts.q);
  p.set("limit", String(opts?.limit ?? 500));
  const data = await getJson<{
    items?: EmpresaListItem[];
    total?: number;
    source?: string;
  }>(`/v1/empresas?${p.toString()}`);
  if (!data?.items) return null;
  return {
    items: data.items,
    total: data.total ?? data.items.length,
    source: data.source || "api",
  };
}

export async function fetchEmpresaDetail(id: string) {
  return getJson<{ ok?: boolean; empresa?: Record<string, unknown>; source?: string }>(
    `/v1/empresas/${encodeURIComponent(id)}`
  );
}
