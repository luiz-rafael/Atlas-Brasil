/**
 * Contas do Brasil — cliente server-side da API /v1/contas/*.
 * O Atlas não acusa. O Atlas documenta.
 */

import "server-only";

export { formatContasValue, formatContasExact } from "@/lib/format";

export type ContasList = {
  items?: Array<Record<string, unknown>>;
  total?: number;
  nota?: string;
  disclaimer?: string;
  error?: string;
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

export type ContasResumo = {
  year: number;
  territory_id?: string;
  disclaimer?: string;
  quanto_entrou?: {
    value?: number;
    unit?: string;
    period?: string;
    source?: string;
    methodology?: string;
  } | null;
  quanto_saiu?: {
    value?: number;
    unit?: string;
    period?: string;
    source?: string;
    methodology?: string;
  } | null;
  resultado_fiscal?: Record<string, unknown> | null;
  divida?: Record<string, unknown> | null;
  renuncia_fiscal?: {
    value?: number;
    unit?: string;
    period?: string;
    source?: string;
    methodology?: string;
  } | null;
  pessoal?: { value?: number; unit?: string; period?: string; source?: string } | null;
  carga_tributaria_pib?: {
    value?: number;
    unit?: string;
    period?: string;
    source?: string;
    methodology?: string;
    amount_brl?: number;
    nota?: string;
  } | null;
  ok?: boolean;
  error?: string;
};

export async function fetchContasResumo(year: number): Promise<ContasResumo | null> {
  return getJson<ContasResumo>(`/v1/contas/resumo?year=${year}`);
}

export async function fetchContasDivida(year: number, limit = 12) {
  return getJson<ContasList>(`/v1/contas/divida?year=${year}&limit=${limit}`);
}

export async function fetchContasResultado(year: number, limit = 12) {
  return getJson<ContasList>(
    `/v1/contas/resultado-fiscal?year=${year}&limit=${limit}`
  );
}

export async function fetchContasRenuncias(
  year: number,
  limit = 20,
  view: "aggregate" | "beneficiarios" = "aggregate"
) {
  return getJson<ContasList>(
    `/v1/contas/renuncias?year=${year}&limit=${limit}&view=${view}`
  );
}

/** Agregados anuais (sem filtro de ano) — série nacional de renúncia. */
export async function fetchContasRenunciasSeries(limit = 40) {
  return getJson<ContasList>(
    `/v1/contas/renuncias?view=aggregate&limit=${limit}`
  );
}

export async function fetchContasPessoal(year: number, limit = 20) {
  return getJson<ContasList>(`/v1/contas/pessoal?year=${year}&limit=${limit}`);
}

export async function fetchContasCno(opts?: { uf?: string; limit?: number }) {
  const uf = opts?.uf ? `&uf=${encodeURIComponent(opts.uf)}` : "";
  const limit = opts?.limit ?? 20;
  return getJson<ContasList>(`/v1/contas/cno?limit=${limit}${uf}`);
}

export type CargaTributariaPoint = {
  year?: number;
  tax_to_gdp_ratio?: number | null;
  pct_pib?: number | null;
  amount_brl?: number | null;
  methodology?: string | null;
};

export async function fetchCargaTributariaSeries() {
  return getJson<{
    ok?: boolean;
    items?: CargaTributariaPoint[];
    total?: number;
    nota?: string;
    disclaimer?: string;
    error?: string;
  }>("/v1/contas/carga-tributaria");
}
