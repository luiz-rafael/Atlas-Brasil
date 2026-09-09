/**
 * Administrations / território contexto — Fase B/C.
 */

import "server-only";

export type Administration = {
  administration_id: string;
  territory_id?: string;
  state_code?: string;
  administration_type?: string;
  executive_person_id?: string | null;
  executive_person_name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  party_at_start?: string | null;
  mandate_id?: string | null;
  election_year?: number | null;
  source?: string;
  disclaimer?: string;
};

export type TerritoryContext = {
  ok?: boolean;
  territory_id: string;
  year: number;
  territory?: Record<string, unknown> | null;
  administration?: Administration | null;
  indicators?: Array<Record<string, unknown>>;
  disclaimer?: string;
  note?: string;
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

export async function fetchAdministrations(opts: {
  state_code?: string;
  territory_id?: string;
  year?: number;
  limit?: number;
}): Promise<Administration[]> {
  const p = new URLSearchParams();
  if (opts.state_code) p.set("state_code", opts.state_code);
  if (opts.territory_id) p.set("territory_id", opts.territory_id);
  if (opts.year != null) p.set("year", String(opts.year));
  p.set("limit", String(opts.limit ?? 200));
  const data = await getJson<{ items?: Administration[] }>(
    `/v1/administrations?${p.toString()}`
  );
  return data?.items || [];
}

export async function fetchTerritoryContext(
  territoryId: string,
  year: number,
  indicators?: string[]
): Promise<TerritoryContext | null> {
  const p = new URLSearchParams();
  p.set("year", String(year));
  if (indicators?.length) p.set("indicators", indicators.join(","));
  return getJson<TerritoryContext>(
    `/v1/territorios/${encodeURIComponent(territoryId)}/contexto?${p.toString()}`
  );
}

export type TerritoryTimelineEvent = {
  event_id?: string;
  event_type?: string;
  label?: string;
  start_date?: string | null;
  end_date?: string | null;
  person_id?: string | null;
  party?: string | null;
  source?: string | null;
};

export async function fetchTerritoryTimeline(
  territoryId: string,
  limit = 40
): Promise<TerritoryTimelineEvent[]> {
  const data = await getJson<{ events?: TerritoryTimelineEvent[] }>(
    `/v1/territorios/${encodeURIComponent(territoryId)}/timeline?limit=${limit}`
  );
  return data?.events || [];
}
