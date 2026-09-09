/**
 * Agrega políticos em exercício por UF e classe de cargo.
 *
 * Escopo Atlas atual: federal (deputados/senadores) + governadores +
 * poucos cargos nacionais. NÃO há coleta de Assembleias Legislativas,
 * prefeituras ou câmaras municipais — UF no perfil = eleito *pelo* estado
 * (bancada federal), não mandato estadual.
 */

export type PoliticoClasse =
  | "governador"
  | "senador"
  | "deputado_federal"
  | "presidente"
  | "outro";

export const POLITICO_CLASSE_LABEL: Record<PoliticoClasse, string> = {
  governador: "Governador(a)",
  senador: "Senador(a)",
  deputado_federal: "Dep. federal",
  presidente: "Presidência",
  outro: "Outros cargos",
};

export type PoliticoSlim = {
  id: string;
  nome: string;
  partido?: string | null;
  cargo_atual?: string | null;
  uf?: string | null;
  foto_url?: string | null;
  classe: PoliticoClasse;
};

export type PoliticosUfSummary = {
  total: number;
  byClass: Partial<Record<PoliticoClasse, number>>;
  sample: PoliticoSlim[];
};

export function classifyPoliticoCargo(
  cargo?: string | null,
  tags?: string[] | null
): PoliticoClasse {
  const c = (cargo || "").toLowerCase();
  const tagBlob = (tags || []).join(" ").toLowerCase();
  const blob = `${c} ${tagBlob}`;

  if (/president|vice[- ]?president|vice_president/.test(blob)) {
    return "presidente";
  }
  if (/governador/.test(blob)) return "governador";
  if (/senador/.test(blob)) return "senador";
  // Câmara dos Deputados — UF = estado pelo qual foi eleito, não AL estadual.
  if (/deputad|camara/.test(blob)) return "deputado_federal";
  return "outro";
}

const SAMPLE_ORDER: PoliticoClasse[] = [
  "governador",
  "senador",
  "deputado_federal",
  "presidente",
  "outro",
];

export function buildPoliticosByUf(
  items: Array<{
    id: string;
    nome: string;
    partido?: string | null;
    cargo_atual?: string | null;
    uf?: string | null;
    foto_url?: string | null;
    tags?: string[] | null;
    no_poder_2026?: boolean;
  }>,
  opts?: { onlyNoPoder?: boolean; samplePerUf?: number }
): Record<string, PoliticosUfSummary> {
  const onlyNoPoder = opts?.onlyNoPoder !== false;
  const samplePerUf = opts?.samplePerUf ?? 8;
  const out: Record<string, PoliticosUfSummary> = {};

  for (const p of items) {
    if (onlyNoPoder && !p.no_poder_2026) continue;
    const uf = (p.uf || "").toUpperCase();
    if (uf.length !== 2) continue;
    const classe = classifyPoliticoCargo(p.cargo_atual, p.tags);
    if (!out[uf]) {
      out[uf] = { total: 0, byClass: {}, sample: [] };
    }
    const bucket = out[uf];
    bucket.total += 1;
    bucket.byClass[classe] = (bucket.byClass[classe] || 0) + 1;
    bucket.sample.push({
      id: p.id,
      nome: p.nome,
      partido: p.partido,
      cargo_atual: p.cargo_atual,
      uf: p.uf,
      foto_url: p.foto_url,
      classe,
    });
  }

  for (const uf of Object.keys(out)) {
    const bucket = out[uf];
    bucket.sample.sort((a, b) => {
      const ia = SAMPLE_ORDER.indexOf(a.classe);
      const ib = SAMPLE_ORDER.indexOf(b.classe);
      if (ia !== ib) return ia - ib;
      return a.nome.localeCompare(b.nome, "pt-BR");
    });
    bucket.sample = bucket.sample.slice(0, samplePerUf);
  }

  return out;
}

/** Classes no tooltip / painel (só o que o Atlas coleta hoje). */
export const TIP_CLASSES: PoliticoClasse[] = [
  "governador",
  "senador",
  "deputado_federal",
];
