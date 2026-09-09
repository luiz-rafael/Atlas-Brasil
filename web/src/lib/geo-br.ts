/**
 * Centroides e agregação territorial a partir da KB + paths dos estados.
 */
import { BR_STATE_PATHS } from "./br-states-paths";

export type UfPoint = { uf: string; x: number; y: number; nome: string };

export const UF_POINTS: UfPoint[] = BR_STATE_PATHS.map((s) => ({
  uf: s.uf,
  x: s.x,
  y: s.y,
  nome: s.nome,
}));

export type TerritoryHotspot = {
  uf: string;
  x: number;
  y: number;
  nome: string;
  weight: number;
  pessoas: number;
  empresas: number;
  instituicoes: number;
  crime: number;
  relacoes: number;
  entityIds: string[];
};

function inferUf(e: {
  uf?: string | null;
  nome?: string;
  tipo?: string;
  tags?: string[];
  cargo_atual?: string | null;
}): string | null {
  if (e.uf) return String(e.uf).toUpperCase();
  const blob = `${e.nome || ""} ${(e.tags || []).join(" ")} ${e.cargo_atual || ""}`.toLowerCase();
  if (
    /stf|tse|stj|congresso|senado|câmara|camara|planalto|brasília|brasilia|pgr|mpf|\bpf\b|cgu|tcu|coaf|presidente da república|ex-presidente/.test(
      blob
    )
  )
    return "DF";
  if (/são paulo|sao paulo|prefeito de s[aã]o|governo de s[aã]o|\bsp\b/.test(blob))
    return "SP";
  if (/rio de janeiro|governo do rio|\brj\b/.test(blob)) return "RJ";
  if (/minas|belo horizonte|\bmg\b/.test(blob)) return "MG";
  if (/bahia|salvador|\bba\b/.test(blob)) return "BA";
  if (/paran[aá]|curitiba|\bpr\b/.test(blob)) return "PR";
  if (/rio grande do sul|porto alegre|\brs\b/.test(blob)) return "RS";
  if (/pernambuco|recife|\bpe\b/.test(blob)) return "PE";
  if (/amazonas|manaus|\bam\b/.test(blob)) return "AM";
  if (/par[aá]\b|bel[eé]m/.test(blob)) return "PA";
  if (/maranh[aã]o|\bma\b/.test(blob)) return "MA";
  if (/alagoas|\bal\b/.test(blob)) return "AL";
  if (
    e.tipo === "partido" ||
    e.tipo === "instituicao" ||
    e.tipo === "caso" ||
    e.tipo === "operacao"
  )
    return "DF";
  if (e.tipo === "faccao") return "SP";
  if (e.tipo === "empresa") return "SP";
  return null;
}

export function buildTerritoryHotspots(kb: {
  entidades: Array<{
    id: string;
    tipo: string;
    uf?: string | null;
    isolada?: boolean;
    tags?: string[];
    nome?: string;
    cargo_atual?: string | null;
  }>;
  relacoes: Array<{ origem: string; destino: string }>;
}): TerritoryHotspot[] {
  const byUf = new Map<string, TerritoryHotspot>();
  for (const p of UF_POINTS) {
    byUf.set(p.uf, {
      uf: p.uf,
      x: p.x,
      y: p.y,
      nome: p.nome,
      weight: 0,
      pessoas: 0,
      empresas: 0,
      instituicoes: 0,
      crime: 0,
      relacoes: 0,
      entityIds: [],
    });
  }

  const idToUf = new Map<string, string>();
  for (const e of kb.entidades) {
    if (e.isolada) continue;
    const uf = inferUf(e);
    if (!uf || !byUf.has(uf)) continue;
    idToUf.set(e.id, uf);
    const h = byUf.get(uf)!;
    h.entityIds.push(e.id);
    if (e.tipo === "pessoa") h.pessoas += 1;
    else if (e.tipo === "empresa") h.empresas += 1;
    else if (e.tipo === "instituicao") h.instituicoes += 1;
    else if (
      e.tipo === "faccao" ||
      (e.tags || []).some((t) => /crime|pcc|cv|faccao/i.test(t))
    )
      h.crime += 1;
    else if (e.tipo === "partido" || e.tipo === "caso" || e.tipo === "operacao")
      h.instituicoes += 1;
  }

  for (const r of kb.relacoes) {
    const u1 = idToUf.get(r.origem);
    const u2 = idToUf.get(r.destino);
    if (u1 && byUf.has(u1)) byUf.get(u1)!.relacoes += 1;
    if (u2 && u2 !== u1 && byUf.has(u2)) byUf.get(u2)!.relacoes += 1;
  }

  Array.from(byUf.values()).forEach((h) => {
    h.weight =
      h.pessoas * 3 +
      h.empresas * 2 +
      h.instituicoes * 2 +
      h.crime * 5 +
      h.relacoes;
  });

  return Array.from(byUf.values()).filter((h) => h.weight > 0);
}
