/**
 * Taxonomia editorial do Atlas de indicadores.
 * Camada 1 = vida da população (entrada). Camada 2 = contas/governo (aprofundamento).
 * Só lista séries que o serving já materializa — categorias sem dado ficam explícitas.
 */

export type AtlasLayer = "vida" | "economia" | "governo";
export type GeoLevel = "STATE" | "MUNICIPALITY";

export type IndicatorDef = {
  id: string;
  label: string;
  levels: readonly GeoLevel[];
  /** Se false, queda do valor é leitura positiva (ex.: mortalidade). */
  higherIsBetter: boolean;
  aggregation: "sum" | "mean";
  unitLabel: string;
};

export type CategoryDef = {
  id: string;
  label: string;
  layer: AtlasLayer;
  /** false = categoria de produto, série ainda não no lake/serving. */
  available: boolean;
  note?: string;
  indicators: readonly IndicatorDef[];
};

export const ATLAS_LAYERS: { id: AtlasLayer; label: string; hint: string }[] = [
  {
    id: "vida",
    label: "Vida da população",
    hint: "Como estava a vida das pessoas neste território e ano.",
  },
  {
    id: "economia",
    label: "Economia",
    hint: "Atividade econômica e mercado de trabalho formal.",
  },
  {
    id: "governo",
    label: "Governo e contas",
    hint: "O que o Estado arrecadou e gastou — não é nota do governante.",
  },
];

export const ATLAS_CATEGORIES: readonly CategoryDef[] = [
  {
    id: "educacao",
    label: "Educação",
    layer: "vida",
    available: true,
    indicators: [
      {
        id: "ind_ideb_anos_iniciais",
        label: "IDEB anos iniciais",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "mean",
        unitLabel: "IDEB 0–10",
      },
      {
        id: "ind_ideb_anos_finais",
        label: "IDEB anos finais",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "mean",
        unitLabel: "IDEB 0–10",
      },
      {
        id: "ind_ideb_ensino_medio",
        label: "IDEB ensino médio",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "mean",
        unitLabel: "IDEB 0–10",
      },
    ],
  },
  {
    id: "saude",
    label: "Saúde",
    layer: "vida",
    available: true,
    indicators: [
      {
        id: "ind_mortalidade_infantil",
        label: "Mortalidade infantil",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: false,
        aggregation: "mean",
        unitLabel: "por 1.000 nascidos",
      },
      {
        id: "ind_mortalidade_geral",
        label: "Mortalidade geral",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: false,
        aggregation: "mean",
        unitLabel: "por 100 mil hab.",
      },
      {
        id: "ind_nascidos_vivos",
        label: "Nascidos vivos",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "pessoas",
      },
      {
        id: "ind_obitos",
        label: "Óbitos",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: false,
        aggregation: "sum",
        unitLabel: "pessoas",
      },
      {
        id: "ind_natalidade",
        label: "Natalidade",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "mean",
        unitLabel: "por 1.000 hab.",
      },
    ],
  },
  {
    id: "seguranca",
    label: "Segurança",
    layer: "vida",
    available: true,
    note: "Taxas e contagens oficiais (SIM/DATASUS e CVLI). No painel, ranking privilegia valores menores.",
    indicators: [
      {
        id: "ind_homicidios_per_100k",
        label: "Homicídios por 100 mil",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: false,
        aggregation: "mean",
        unitLabel: "por 100 mil hab.",
      },
      {
        id: "ind_homicidios",
        label: "Homicídios (contagem)",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: false,
        aggregation: "sum",
        unitLabel: "óbitos",
      },
      {
        id: "ind_cvli_per_100k",
        label: "CVLI por 100 mil",
        levels: ["STATE"],
        higherIsBetter: false,
        aggregation: "mean",
        unitLabel: "por 100 mil hab.",
      },
      {
        id: "ind_mortes_causas_externas",
        label: "Mortes por causas externas",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: false,
        aggregation: "sum",
        unitLabel: "óbitos",
      },
    ],
  },
  {
    id: "saneamento",
    label: "Saneamento",
    layer: "vida",
    available: false,
    note: "Água, esgoto e cobertura ainda não estão no serving desta página.",
    indicators: [],
  },
  {
    id: "desenvolvimento",
    label: "Desenvolvimento",
    layer: "vida",
    available: true,
    indicators: [
      {
        id: "ind_pop_estimada",
        label: "População",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "pessoas",
      },
    ],
  },
  {
    id: "trabalho",
    label: "Emprego",
    layer: "economia",
    available: true,
    indicators: [
      {
        id: "ind_caged_saldo",
        label: "Saldo formal (CAGED)",
        levels: ["STATE"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "vínculos",
      },
      {
        id: "ind_caged_admissoes",
        label: "Admissões",
        levels: ["STATE"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "vínculos",
      },
      {
        id: "ind_caged_desligamentos",
        label: "Desligamentos",
        levels: ["STATE"],
        higherIsBetter: false,
        aggregation: "sum",
        unitLabel: "vínculos",
      },
    ],
  },
  {
    id: "economia",
    label: "Economia",
    layer: "economia",
    available: true,
    indicators: [
      {
        id: "ind_pib_corrente",
        label: "PIB",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "mil R$ (nominal)",
      },
      {
        id: "ind_pib_per_capita",
        label: "PIB per capita",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "mean",
        unitLabel: "R$/hab (nominal)",
      },
    ],
  },
  {
    id: "contas",
    label: "Contas públicas",
    layer: "governo",
    available: true,
    note:
      "Receitas e despesas territoriais. Renúncia fiscal federal é agregado Brasil — beneficiários em Contas.",
    indicators: [
      {
        id: "ind_receita_bruta",
        label: "Receita bruta",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "R$ (nominal)",
      },
      {
        id: "ind_despesa_total",
        label: "Despesa total",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "R$ (nominal)",
      },
      {
        id: "ind_rcl",
        label: "RCL",
        levels: ["STATE"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "R$ (nominal)",
      },
      {
        id: "ind_despesa_pessoal",
        label: "Pessoal",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "R$ (nominal)",
      },
      {
        id: "ind_despesa_investimentos",
        label: "Investimentos",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "R$ (nominal)",
      },
      {
        id: "ind_despesa_saude",
        label: "Despesa em saúde",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "R$ (nominal)",
      },
      {
        id: "ind_despesa_educacao",
        label: "Despesa em educação",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "sum",
        unitLabel: "R$ (nominal)",
      },
      {
        id: "ind_despesa_saude_per_capita",
        label: "Saúde per capita",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "mean",
        unitLabel: "R$/hab (nominal)",
      },
      {
        id: "ind_despesa_educacao_per_capita",
        label: "Educação per capita",
        levels: ["STATE", "MUNICIPALITY"],
        higherIsBetter: true,
        aggregation: "mean",
        unitLabel: "R$/hab (nominal)",
      },
      {
        id: "ind_renuncia_fiscal",
        label: "Renúncia fiscal federal",
        levels: ["STATE"],
        higherIsBetter: false,
        aggregation: "sum",
        unitLabel: "R$ (nominal)",
      },
    ],
  },
] as const;

export const ALL_ATLAS_INDICATORS: IndicatorDef[] = ATLAS_CATEGORIES.flatMap(
  (c) => [...c.indicators]
);

export function indicatorDef(id: string): IndicatorDef | undefined {
  return ALL_ATLAS_INDICATORS.find((i) => i.id === id);
}

export function categoryOf(indicatorId: string): CategoryDef | undefined {
  return ATLAS_CATEGORIES.find((c) =>
    c.indicators.some((i) => i.id === indicatorId)
  );
}

export function categoriesForLayer(layer: AtlasLayer): CategoryDef[] {
  return ATLAS_CATEGORIES.filter((c) => c.layer === layer);
}

/** Ordem editorial (vida primeiro; contas por último). */
export const PRIMARY_CATEGORY_IDS = [
  "educacao",
  "saude",
  "seguranca",
  "trabalho",
  "saneamento",
  "desenvolvimento",
  "economia",
  "contas",
] as const;

export function availableCategories(): CategoryDef[] {
  const byId = Object.fromEntries(ATLAS_CATEGORIES.map((c) => [c.id, c]));
  return PRIMARY_CATEGORY_IDS.map((id) => byId[id]).filter(
    (c): c is CategoryDef => !!c && c.available && c.indicators.length > 0
  );
}

export function domainCssVar(categoryId: string): string {
  const map: Record<string, string> = {
    educacao: "var(--atlas-domain-educacao)",
    saude: "var(--atlas-domain-saude)",
    seguranca: "var(--atlas-domain-seguranca)",
    trabalho: "var(--atlas-domain-emprego)",
    saneamento: "var(--atlas-domain-saneamento)",
    desenvolvimento: "var(--atlas-domain-desenvolvimento)",
    economia: "var(--atlas-domain-economia)",
    contas: "var(--atlas-domain-contas)",
  };
  return map[categoryId] || "var(--atlas-blue)";
}

/** Hex do domínio para escala do mapa (client). */
export function domainHex(categoryId: string): string {
  const map: Record<string, string> = {
    educacao: "#315D78",
    saude: "#3F7564",
    seguranca: "#9B5842",
    trabalho: "#A47B32",
    saneamento: "#39758A",
    desenvolvimento: "#66736F",
    economia: "#A47B32",
    contas: "#B39645",
  };
  return map[categoryId] || "#285A78";
}

export function defaultIndicatorFor(
  layer: AtlasLayer,
  categoryId?: string
): string {
  const cats = categoriesForLayer(layer).filter((c) => c.available);
  const cat =
    (categoryId && cats.find((c) => c.id === categoryId)) ||
    cats.find((c) => c.indicators.length) ||
    cats[0];
  return cat?.indicators[0]?.id || "ind_pop_estimada";
}

export function resolveAtlasSelection(opts: {
  layer?: string;
  cat?: string;
  ind?: string;
}): { layer: AtlasLayer; category: CategoryDef; indicator: IndicatorDef } {
  const rawInd = opts.ind && indicatorDef(opts.ind);
  if (rawInd) {
    const category = categoryOf(rawInd.id)!;
    return { layer: category.layer, category, indicator: rawInd };
  }
  const available = availableCategories();
  const byCat = available.find((c) => c.id === opts.cat);
  if (byCat) {
    return {
      layer: byCat.layer,
      category: byCat,
      indicator: byCat.indicators[0],
    };
  }
  // compat: se só veio camada, primeira categoria da camada
  if (opts.layer && ATLAS_LAYERS.some((l) => l.id === opts.layer)) {
    const cats = categoriesForLayer(opts.layer as AtlasLayer).filter(
      (c) => c.available
    );
    const category = cats[0] || available[0];
    return {
      layer: category.layer,
      category,
      indicator: category.indicators[0],
    };
  }
  const category = available[0];
  return {
    layer: category.layer,
    category,
    indicator: category.indicators[0],
  };
}

export function brasilAggregate(
  values: Record<string, number>,
  aggregation: "sum" | "mean"
): number | null {
  const nums = Object.values(values).filter((v) => Number.isFinite(v));
  if (!nums.length) return null;
  const sum = nums.reduce((a, b) => a + b, 0);
  return aggregation === "sum" ? sum : sum / nums.length;
}

export function rankAmong(
  values: Record<string, number>,
  uf: string,
  higherIsBetter: boolean
): { rank: number; total: number } | null {
  const entries = Object.entries(values).filter(([, v]) => Number.isFinite(v));
  if (!entries.length || values[uf] == null) return null;
  const sorted = [...entries].sort((a, b) =>
    higherIsBetter ? b[1] - a[1] : a[1] - b[1]
  );
  const idx = sorted.findIndex(([k]) => k === uf);
  if (idx < 0) return null;
  return { rank: idx + 1, total: sorted.length };
}

export function shortPersonName(name: string | null | undefined): string {
  if (!name) return "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  if (parts.length === 1) return titleCaseToken(parts[0]);
  const skip = new Set(["da", "de", "do", "dos", "das", "e", "di", "del", "della"]);
  const last =
    [...parts].reverse().find((p) => !skip.has(p.toLowerCase())) ||
    parts[parts.length - 1];
  return titleCaseToken(last);
}

function titleCaseToken(s: string): string {
  if (!s) return "";
  if (s === s.toUpperCase() || s === s.toLowerCase()) {
    return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
  }
  return s;
}

/**
 * Rótulo no mapa: primeiro + segundo nome (ex.: "Romeu Zema", "João Doria").
 * Mais reconhecível e estável que só o sobrenome.
 */
export function mapGovernorLabel(
  name: string | null | undefined,
  opts?: { compact?: boolean }
): string {
  if (!name) return "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  const skip = new Set(["da", "de", "do", "dos", "das", "e", "di", "del", "della"]);
  // primeiro e segundo nome significativos (pula partículas)
  const significant = parts.filter((p) => !skip.has(p.toLowerCase()));
  if (!significant.length) return titleCaseToken(parts[0]);
  const first = titleCaseToken(significant[0]);
  if (significant.length === 1) return first;
  const second = titleCaseToken(significant[1]);
  if (opts?.compact) return `${first.charAt(0)}. ${second}`;
  return `${first} ${second}`;
}

/** Duas linhas para o SVG: [primeiro, segundo]. */
export function mapGovernorLines(
  name: string | null | undefined,
  opts?: { compact?: boolean }
): [string, string] | null {
  const label = mapGovernorLabel(name, opts);
  if (!label) return null;
  const bits = label.split(/\s+/);
  if (bits.length === 1) return [bits[0], ""];
  // "R. Zema" compact → uma linha; "Romeu Zema" → duas
  if (bits[0].endsWith(".") && bits.length === 2) return [label, ""];
  return [bits[0], bits.slice(1).join(" ")];
}

export function yearInAdminRange(
  year: number,
  start?: string | null,
  end?: string | null
): boolean {
  const y0 = start ? Number(String(start).slice(0, 4)) : null;
  const y1 = end ? Number(String(end).slice(0, 4)) : null;
  if (y0 != null && !Number.isNaN(y0) && year < y0) return false;
  if (y1 != null && !Number.isNaN(y1) && year >= y1) return false;
  return true;
}

/** Indicadores-resumo da “visão do período” (não são nota de governo). */
export const PERIOD_SNAPSHOT_IDS = [
  "ind_ideb_anos_iniciais",
  "ind_mortalidade_infantil",
  "ind_homicidios_per_100k",
  "ind_caged_saldo",
  "ind_pop_estimada",
  "ind_pib_per_capita",
] as const;
