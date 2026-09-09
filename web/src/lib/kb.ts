import "server-only";
/**
 * KB servida ao site.
 * Lê `data/atlas-brasil-kb-web.json` (export enxuto) via fs — a gold completa
 * (~580MB) estoura o limite de string do Node/webpack.
 * Gere com: `python pipelines/load/export_kb_web.py`
 */
import fs from "fs";
import path from "path";
import type {
  Entidade,
  Caso,
  Registro,
  Relacao,
} from "./kb-types";
import { foldAccents } from "./text-fold";

export type { Entidade, Caso, Registro, Relacao } from "./kb-types";

export type Marco = {
  id: string;
  data: string;
  eixo: string;
  titulo: string;
  caso_ids?: string[];
  governo_id?: string;
  fontes?: string[];
};

export type Fluxo = {
  id: string;
  origem: string;
  intermediarios?: string[];
  destino: string;
  valor_suspeito?: number | null;
  valor_investigado?: number | null;
  valor_bloqueado?: number | null;
  valor_denunciado?: number | null;
  valor_comprovado_desviado?: number | null;
  moeda?: string;
  natureza: string;
  caso_id: string;
  grau_confirmacao: string;
  fontes: string[];
  nota?: string;
};

export type Dossie = {
  status_atual?: string;
  o_que_aconteceu?: string;
  como_comecou?: string;
  contexto?: string;
  investigacao?: string;
  justica?: string;
  por_que_terminou?: string;
  consequencias?: string;
  situacao_2026?: string;
  fontes_chave?: string[];
};

export type Documento = {
  id: string;
  tipo?: string;
  titulo: string;
  data?: string;
  nivel_fonte?: string;
  orgao?: string;
  casos?: string[];
  url?: string;
  url_ref?: string;
};

export type KB = {
  meta: Record<string, unknown>;
  casos: Caso[];
  entidades: Entidade[];
  registros_pessoa_caso: Registro[];
  relacoes: Relacao[];
  fluxos_financeiros?: Fluxo[];
  eventos_mecanismo?: Array<Record<string, unknown>>;
  timeline: Marco[];
  documentos?: Documento[];
  dossies?: Record<string, Dossie>;
  mapa_poder_2026?: Record<string, string>;
  dossie_centrao?: Record<string, unknown>;
  analise_causal?: Array<Record<string, unknown>>;
  governos?: Array<{
    id: string;
    presidente: string;
    inicio: string;
    fim: string;
  }>;
};

let _kb: KB | null = null;

function emptyKb(): KB {
  return {
    meta: {
      versao: "empty",
      _empty: true,
      nota: "KB ausente no deploy — UI usa API/Postgres quando disponível.",
    },
    casos: [],
    entidades: [],
    registros_pessoa_caso: [],
    relacoes: [],
    timeline: [],
    documentos: [],
    dossies: {},
    mapa_poder_2026: {},
  };
}

function resolveKbPath(): string | null {
  const candidates = [
    process.env.ATLAS_KB_WEB_PATH,
    path.join(process.cwd(), "..", "data", "atlas-brasil-kb-web.json"),
    path.join(process.cwd(), "data", "atlas-brasil-kb-web.json"),
  ].filter(Boolean) as string[];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

/** KB em memória (fs) — só Server Components / Route Handlers. */
export function getKB(): KB {
  if (!_kb) {
    const kbPath = resolveKbPath();
    if (!kbPath) {
      _kb = emptyKb();
      return _kb;
    }
    const raw = fs.readFileSync(kbPath, "utf8");
    _kb = JSON.parse(raw) as KB;
  }
  return _kb;
}

let _entById: Map<string, Entidade> | null = null;
let _casoById: Map<string, Caso> | null = null;
let _relsByEnt: Map<string, Relacao[]> | null = null;
let _regsByPessoa: Map<string, Registro[]> | null = null;

function entIndex(): Map<string, Entidade> {
  if (!_entById) {
    _entById = new Map(getKB().entidades.map((e) => [e.id, e]));
  }
  return _entById;
}

function casoIndex(): Map<string, Caso> {
  if (!_casoById) {
    _casoById = new Map(getKB().casos.map((c) => [c.id, c]));
  }
  return _casoById;
}

function relsIndex(): Map<string, Relacao[]> {
  if (!_relsByEnt) {
    const m = new Map<string, Relacao[]>();
    for (const r of getKB().relacoes) {
      if (!m.has(r.origem)) m.set(r.origem, []);
      if (!m.has(r.destino)) m.set(r.destino, []);
      m.get(r.origem)!.push(r);
      if (r.origem !== r.destino) m.get(r.destino)!.push(r);
    }
    _relsByEnt = m;
  }
  return _relsByEnt;
}

function regsPessoaIndex(): Map<string, Registro[]> {
  if (!_regsByPessoa) {
    const m = new Map<string, Registro[]>();
    for (const r of getKB().registros_pessoa_caso) {
      if (!m.has(r.pessoa_id)) m.set(r.pessoa_id, []);
      m.get(r.pessoa_id)!.push(r);
    }
    _regsByPessoa = m;
  }
  return _regsByPessoa;
}

export function entityById(id: string): Entidade | undefined {
  return entIndex().get(id);
}

export function casoById(id: string): Caso | undefined {
  return casoIndex().get(id);
}

export function labelOf(id: string): string {
  return entityById(id)?.nome || casoById(id)?.nome || id;
}

export function relacoesDe(id: string): Relacao[] {
  return relsIndex().get(id) || [];
}

export function registrosDePessoa(pessoaId: string): Registro[] {
  return regsPessoaIndex().get(pessoaId) || [];
}

/** Cópia enxuta para RSC/client — evita mandar 200KB+ de listas por request. */
export function slimPessoaForWeb(pessoa: Entidade): Entidade {
  const leg = pessoa.legislativo_resumo;
  if (!leg) return pessoa;
  const lista = leg.proposicoes_lista || [];
  return {
    ...pessoa,
    legislativo_resumo: {
      ...leg,
      proposicao_ids: undefined,
      proposicoes_lista: lista.slice(0, 80),
      proposicoes_sample: (leg.proposicoes_sample || lista).slice(0, 12),
      votos_por_proposicao: (leg.votos_por_proposicao || []).slice(0, 30),
      votos_projetos: (leg.votos_projetos || []).slice(0, 24),
    },
  };
}

/** Ego 1-hop só com relações da pessoa (sem varrer 100k nós do grafo). */
export function egoNeighborhood(centroId: string) {
  const rels = relacoesDe(centroId);
  const ids = new Set<string>([centroId]);
  for (const r of rels) {
    ids.add(r.origem);
    ids.add(r.destino);
  }
  const nodes = [...ids].map((id) => {
    const e = entityById(id);
    const c = !e ? casoById(id) : undefined;
    return {
      id,
      nome: e?.nome || c?.nome || id,
      tipo: e?.tipo || (c ? "caso" : "desconhecido"),
    };
  });
  const edges = rels.map((r) => ({
    id: r.id,
    from: r.origem,
    to: r.destino,
    tipo: r.tipo,
    grau_confirmacao: r.grau_confirmacao,
    justificativa_documental: r.justificativa_documental,
    contexto: r.contexto,
    periodo: r.periodo,
  }));
  return { nodes, edges };
}

export function pessoas(filters?: {
  q?: string;
  partido?: string;
  no_poder?: string;
  tag?: string;
}): Entidade[] {
  let list = getKB().entidades.filter((e) => e.tipo === "pessoa");
  if (filters?.partido)
    list = list.filter(
      (e) => (e.partido || "").toLowerCase() === filters.partido!.toLowerCase()
    );
  if (filters?.no_poder === "sim") list = list.filter((e) => e.no_poder_2026);
  if (filters?.no_poder === "nao") list = list.filter((e) => !e.no_poder_2026);
  if (filters?.tag)
    list = list.filter((e) => e.tags?.includes(filters.tag!));
  if (filters?.q) {
    const tokens = foldAccents(filters.q)
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    list = list.filter((e) => {
      const blob = foldAccents(
        [e.nome, e.partido, e.cargo_atual].map((x) => String(x || "")).join(" ")
      );
      return tokens.every((t) => blob.includes(t));
    });
  }
  return list;
}

export function buscaGlobal(q: string) {
  const s = q.trim().toLowerCase();
  if (!s) return { pessoas: [], empresas: [], partidos: [], casos: [], instituicoes: [] };
  const kb = getKB();
  return {
    pessoas: kb.entidades.filter(
      (e) => e.tipo === "pessoa" && e.nome.toLowerCase().includes(s)
    ),
    empresas: kb.entidades.filter(
      (e) => e.tipo === "empresa" && e.nome.toLowerCase().includes(s)
    ),
    partidos: kb.entidades.filter(
      (e) => e.tipo === "partido" && e.nome.toLowerCase().includes(s)
    ),
    instituicoes: kb.entidades.filter(
      (e) => e.tipo === "instituicao" && e.nome.toLowerCase().includes(s)
    ),
    casos: kb.casos.filter((c) => c.nome.toLowerCase().includes(s)),
  };
}

export function registrosDeCaso(casoId: string): Registro[] {
  return getKB().registros_pessoa_caso.filter((r) => r.caso_id === casoId);
}

export { formatBRL, STATUS_LABEL } from "./format";

export function dossieDe(casoId: string): Dossie | undefined {
  return getKB().dossies?.[casoId];
}

export function documentos(filters?: {
  nivel?: string;
  orgao?: string;
  caso_id?: string;
}): Documento[] {
  let list = getKB().documentos || [];
  if (filters?.nivel)
    list = list.filter((d) => d.nivel_fonte === filters.nivel);
  if (filters?.orgao)
    list = list.filter(
      (d) => (d.orgao || "").toLowerCase() === filters.orgao!.toLowerCase()
    );
  if (filters?.caso_id)
    list = list.filter((d) => d.casos?.includes(filters.caso_id!));
  return list;
}

/** Fase C: ATLAS_FONTES_SOURCE=api → FastAPI/Postgres; senão KB JSON. */
export async function documentosServing(filters?: {
  nivel?: string;
  orgao?: string;
  caso_id?: string;
  q?: string;
}): Promise<Documento[]> {
  const src = (
    process.env.ATLAS_FONTES_SOURCE ||
    process.env.NEXT_PUBLIC_ATLAS_FONTES_SOURCE ||
    "api"
  ).toLowerCase();
  if (src === "api" && !filters?.caso_id) {
    const base = (
      process.env.ATLAS_API_URL ||
      process.env.NEXT_PUBLIC_ATLAS_API_URL ||
      process.env.NEXT_PUBLIC_ATLAS_API ||
      "http://localhost:8001"
    ).replace(/\/$/, "");
    const qs = new URLSearchParams();
    if (filters?.nivel) qs.set("nivel", filters.nivel);
    if (filters?.orgao) qs.set("orgao", filters.orgao);
    try {
      const res = await fetch(`${base}/v1/fontes?${qs}`, {
        next: { revalidate: 120 },
      });
      if (res.ok) {
        let list = (await res.json()) as Documento[];
        if (filters?.q) {
          const s = filters.q.toLowerCase();
          list = list.filter(
            (d) =>
              (d.titulo || "").toLowerCase().includes(s) ||
              (d.orgao || "").toLowerCase().includes(s)
          );
        }
        return list;
      }
    } catch {
      /* fallback KB */
    }
  }
  let list = documentos(filters);
  if (filters?.q) {
    const s = filters.q.toLowerCase();
    list = list.filter(
      (d) =>
        d.titulo.toLowerCase().includes(s) ||
        (d.orgao || "").toLowerCase().includes(s)
    );
  }
  return list;
}
