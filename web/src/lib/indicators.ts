/**
 * Camada territorial / indicadores.
 * Fase C: ATLAS_INDICATORS_SOURCE=api (default) lê FastAPI/Postgres;
 * fallback para data/atlas-brasil-indicators.json.
 */

import "server-only";
import fs from "fs";
import path from "path";
import {
  formatPop as formatPopShared,
  formatPibMilReais as formatPibMilReaisShared,
  formatReais as formatReaisShared,
  formatIndicatorValue as formatIndicatorValueShared,
} from "./format";

export type Territory = {
  territory_id: string;
  ibge_code?: string;
  name?: string;
  territory_type?: string;
  state_code?: string;
  state_name?: string;
  region_code?: string;
  region_name?: string;
};

export type Indicator = {
  indicator_id: string;
  name?: string;
  display_name?: string;
  description?: string;
  category?: string;
  unit?: string;
  methodology_url?: string;
  notes?: string;
  source_id?: string;
  dataset_id?: string;
  minimum_geographic_level?: string;
};

export type Observation = {
  observation_id: string;
  indicator_id: string;
  territory_id: string;
  reference_year: number;
  value: number;
  value_reais?: number;
  unit?: string;
  source_id?: string;
  dataset_id?: string;
  period_start?: string;
  period_end?: string;
  fonte_url?: string;
  geographic_level?: string;
};

export type IndicatorsDB = {
  meta: {
    em?: string;
    principio?: string;
    disclaimer?: string;
    territories?: number;
    indicators?: number;
    observations?: number;
  };
  territories: Territory[];
  indicators: Indicator[];
  observations: Observation[];
};

let _fileCache: IndicatorsDB | null = null;
let _catalogCache: { territories: Territory[]; indicators: Indicator[] } | null =
  null;

function indicatorsSource(): "api" | "file" {
  const v = (
    process.env.ATLAS_INDICATORS_SOURCE ||
    process.env.NEXT_PUBLIC_ATLAS_INDICATORS_SOURCE ||
    "api"
  ).toLowerCase();
  return v === "file" ? "file" : "api";
}

function apiBase(): string {
  return (
    process.env.ATLAS_API_URL ||
    process.env.NEXT_PUBLIC_ATLAS_API_URL ||
    process.env.NEXT_PUBLIC_ATLAS_API ||
    "http://localhost:8001"
  ).replace(/\/$/, "");
}

async function apiGet<T>(pathQs: string): Promise<T | null> {
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

function indicatorsPathCandidates(): string[] {
  return [
    path.join(process.cwd(), "..", "data", "atlas-brasil-indicators.json"),
    path.join(process.cwd(), "data", "atlas-brasil-indicators.json"),
  ];
}

function loadFileDb(): IndicatorsDB {
  if (_fileCache) return _fileCache;
  const empty: IndicatorsDB = {
    meta: {
      disclaimer:
        "Arquivo de indicadores ainda não gerado. Rode pipelines/run_indicadores.py.",
    },
    territories: [],
    indicators: [],
    observations: [],
  };
  const p = indicatorsPathCandidates().find((x) => fs.existsSync(x));
  if (!p) {
    _fileCache = empty;
    return _fileCache;
  }
  try {
    const size = fs.statSync(p).size;
    // Evita OOM: dump legado pode passar de centenas de MB.
    if (size > 80 * 1024 * 1024) {
      _fileCache = {
        ...empty,
        meta: {
          ...empty.meta,
          disclaimer:
            "Fallback arquivo de indicadores omitido (arquivo grande). Use a API.",
        },
      };
      return _fileCache;
    }
    _fileCache = JSON.parse(fs.readFileSync(p, "utf-8")) as IndicatorsDB;
  } catch {
    _fileCache = empty;
  }
  return _fileCache!;
}

/** Sync — só arquivo (legado / fallback interno). */
export function getIndicators(): IndicatorsDB {
  return loadFileDb();
}

export async function getCatalog(): Promise<{
  territories: Territory[];
  indicators: Indicator[];
  meta: IndicatorsDB["meta"];
  source: string;
}> {
  if (indicatorsSource() === "api") {
    const data = await apiGet<{
      indicators?: Indicator[];
      territories?: Territory[];
      meta?: IndicatorsDB["meta"];
    }>("/v1/indicadores?include_territories=true");
    if (data?.indicators?.length) {
      _catalogCache = {
        territories: data.territories || [],
        indicators: data.indicators,
      };
      return {
        territories: _catalogCache.territories,
        indicators: _catalogCache.indicators,
        meta: data.meta || {},
        source: "api",
      };
    }
  }
  const db = loadFileDb();
  return {
    territories: db.territories,
    indicators: db.indicators,
    meta: db.meta,
    source: "file",
  };
}

export async function listYears(
  indicatorId = "ind_pop_estimada"
): Promise<number[]> {
  if (indicatorsSource() === "api") {
    const data = await apiGet<{ years?: number[] }>(
      `/v1/indicadores/years?indicator_id=${encodeURIComponent(indicatorId)}`
    );
    if (data?.years?.length) return data.years;
  }
  const years = new Set<number>();
  for (const o of loadFileDb().observations) {
    if (o.indicator_id === indicatorId) years.add(o.reference_year);
  }
  return Array.from(years).sort((a, b) => a - b);
}

export async function observationsForYear(
  year: number,
  indicatorId = "ind_pop_estimada",
  opts?: { level?: "STATE" | "MUNICIPALITY"; uf?: string }
): Promise<Observation[]> {
  if (indicatorsSource() === "api") {
    const qs = new URLSearchParams({
      indicator_id: indicatorId,
      year: String(year),
    });
    if (opts?.level) qs.set("level", opts.level);
    if (opts?.uf) qs.set("uf", opts.uf);
    const data = await apiGet<{ observations?: Observation[] }>(
      `/v1/indicadores/observations?${qs}`
    );
    if (data?.observations) return data.observations;
  }
  const db = loadFileDb();
  return db.observations.filter((o) => {
    if (o.indicator_id !== indicatorId || o.reference_year !== year) return false;
    if (opts?.level === "STATE") return o.territory_id.startsWith("uf_");
    if (opts?.level === "MUNICIPALITY") {
      if (!o.territory_id.startsWith("mun_")) return false;
      if (opts.uf) {
        const t = db.territories.find((x) => x.territory_id === o.territory_id);
        return (t?.state_code || "").toUpperCase() === opts.uf.toUpperCase();
      }
      return true;
    }
    return true;
  });
}

export async function seriesForTerritory(
  territoryId: string,
  indicatorId = "ind_pop_estimada"
): Promise<Observation[]> {
  if (indicatorsSource() === "api") {
    const qs = new URLSearchParams({
      territory_id: territoryId,
      indicator_id: indicatorId,
    });
    const data = await apiGet<{ observations?: Observation[] }>(
      `/v1/indicadores/series?${qs}`
    );
    if (data?.observations) {
      return [...data.observations].sort(
        (a, b) => a.reference_year - b.reference_year
      );
    }
  }
  return loadFileDb()
    .observations.filter(
      (o) => o.territory_id === territoryId && o.indicator_id === indicatorId
    )
    .sort((a, b) => a.reference_year - b.reference_year);
}

/** Anos do mandato: inicio inclusivo, fim exclusivo se for 01-01 do ano seguinte. */
export function mandateYearRange(inicio?: string | null, fim?: string | null): {
  from: number | null;
  toExclusive: number | null;
} {
  const from = inicio ? Number(String(inicio).slice(0, 4)) : null;
  let toExclusive = fim ? Number(String(fim).slice(0, 4)) : null;
  if (from != null && Number.isNaN(from)) return { from: null, toExclusive: null };
  if (toExclusive != null && Number.isNaN(toExclusive)) toExclusive = null;
  return {
    from: from != null && !Number.isNaN(from) ? from : null,
    toExclusive:
      toExclusive != null && !Number.isNaN(toExclusive) ? toExclusive : null,
  };
}

export async function seriesDuringYears(
  territoryId: string,
  indicatorId: string,
  yearFrom: number,
  yearToExclusive: number
): Promise<Observation[]> {
  const series = await seriesForTerritory(territoryId, indicatorId);
  return series.filter(
    (o) => o.reference_year >= yearFrom && o.reference_year < yearToExclusive
  );
}

export async function seriesForMandate(
  m: { uf?: string | null; inicio?: string | null; fim?: string | null },
  indicatorId = "ind_pib_corrente"
): Promise<Observation[]> {
  const uf = (m.uf || "").toUpperCase();
  if (!uf) return [];
  const { from, toExclusive } = mandateYearRange(m.inicio, m.fim);
  if (from == null || toExclusive == null || toExclusive <= from) return [];
  return seriesDuringYears(`uf_${uf}`, indicatorId, from, toExclusive);
}

export async function ufValuesMap(
  year: number,
  indicatorId = "ind_pop_estimada"
): Promise<Record<string, number>> {
  if (indicatorsSource() === "api") {
    const qs = new URLSearchParams({
      year: String(year),
      indicator_id: indicatorId,
    });
    const data = await apiGet<{ values?: Record<string, number> }>(
      `/v1/indicadores/choropleth?${qs}`
    );
    if (data?.values && Object.keys(data.values).length) return data.values;
  }
  const out: Record<string, number> = {};
  for (const o of await observationsForYear(year, indicatorId, {
    level: "STATE",
  })) {
    const uf = o.territory_id.replace(/^uf_/, "");
    if (uf.length === 2) out[uf] = o.value;
  }
  return out;
}

export async function municipalitiesOfUf(uf: string): Promise<Territory[]> {
  const u = uf.toUpperCase();
  const cat = await getCatalog();
  return cat.territories.filter(
    (t) => t.territory_type === "MUNICIPALITY" && t.state_code === u
  );
}

export function formatPop(n: number): string {
  return formatPopShared(n);
}

/** PIB SIDRA vem em mil reais; exibe em R$ (reais). */
export function formatPibMilReais(milReais: number): string {
  return formatPibMilReaisShared(milReais);
}

export function formatReais(n: number): string {
  return formatReaisShared(n);
}

export function formatIndicatorValue(
  indicatorId: string,
  value: number
): string {
  return formatIndicatorValueShared(indicatorId, value);
}
