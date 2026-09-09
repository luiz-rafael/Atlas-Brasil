/**
 * Magistrados / remuneração CNJ — cliente server-side.
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
      next: { revalidate: 120 },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export type MagStatsPoint = {
  year?: number;
  month?: number;
  period?: string;
  n_rows?: number;
  n_magistrates?: number;
  sum_gross?: number | null;
  avg_gross?: number | null;
  sum_net?: number | null;
  avg_net?: number | null;
  sum_subsidy?: number | null;
  avg_subsidy?: number | null;
};

export type MagStats = {
  ok?: boolean;
  error?: string;
  disclaimer?: string;
  coverage_note?: string;
  courts?: Array<{ court_id: string; magistrates: number }>;
  years?: number[];
  latest_period?: MagStatsPoint | null;
  timeline?: MagStatsPoint[];
  by_court?: Array<{
    court_id: string;
    n_rows?: number;
    n_magistrates?: number;
    sum_gross?: number | null;
    avg_gross?: number | null;
    sum_net?: number | null;
    avg_subsidy?: number | null;
  }>;
  top_avg_gross?: Array<{
    magistrate_id: string;
    display_name?: string | null;
    court_id?: string;
    avg_gross?: number | null;
    avg_net?: number | null;
    avg_subsidy?: number | null;
    n_months?: number;
  }>;
  top_year?: number | null;
  source?: string;
};

export async function fetchMagistradosStats(opts?: {
  court_id?: string;
  year?: number;
}): Promise<MagStats | null> {
  const p = new URLSearchParams();
  if (opts?.court_id) p.set("court_id", opts.court_id);
  if (opts?.year != null) p.set("year", String(opts.year));
  const qs = p.toString();
  return getJson<MagStats>(
    `/v1/magistrados/stats${qs ? `?${qs}` : ""}`
  );
}

export async function fetchMagistradoDetail(id: string) {
  return getJson<{
    magistrado?: Record<string, unknown>;
    compensations?: Array<Record<string, unknown>>;
    disclaimer?: string;
    source?: string;
  }>(`/v1/magistrados/${encodeURIComponent(id)}`);
}
