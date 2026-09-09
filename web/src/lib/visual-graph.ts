/**
 * FASE 8 — VISUAL_GRAPH_SERVICE
 * Macro → micro: supernós de domínio, zoom semântico, diversified top-k.
 * O frontend não faz traversal gigante; este serviço limita nós/arestas.
 */

import "server-only";
import {
  GRAPH_LIMITS,
  PATH_DISCLAIMER,
  loadGraph,
  type GraphEdge,
  type GraphNode,
  subgraph,
  capSubgraph,
} from "./graph-engine";

export type GraphMode =
  | "resumo"
  | "politica"
  | "dinheiro"
  | "empresas"
  | "justica"
  | "completo";

export type DomainKey = "politica" | "dinheiro" | "empresas" | "justica";

export type ExpandableGroup = {
  id: string;
  domain: DomainKey;
  subtype?: string;
  label: string;
  count: number;
  mode: GraphMode;
  expand?: string;
};

export type VisualGraphResult = {
  focal: string;
  mode: GraphMode;
  expand: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  supernodes: GraphNode[];
  expandable_groups: ExpandableGroup[];
  domain_counts: Record<DomainKey, number>;
  hidden_count: number;
  reason_codes: string[];
  disclaimer: string;
  motor: "memoria";
};

const DOMAIN_LABEL: Record<DomainKey, string> = {
  politica: "POLÍTICA",
  dinheiro: "DINHEIRO",
  empresas: "EMPRESAS",
  justica: "JUSTIÇA",
};

const SUBTYPE_LABEL: Record<string, string> = {
  emenda: "EMENDAS",
  campanha: "CAMPANHAS",
  despesa: "DESPESAS",
  transferencia: "TRANSFERÊNCIAS",
  contrato: "CONTRATOS",
  licitacao: "LICITAÇÕES",
  partido: "PARTIDOS",
  mandato: "MANDATOS",
  proposicao: "PROPOSIÇÕES",
  frente: "FRENTES/ÓRGÃOS",
  caso: "PROCESSOS/CASOS",
  empresa: "EMPRESAS",
  outros: "OUTROS",
};

function yearOf(periodo?: string): number | null {
  if (!periodo) return null;
  const m = periodo.match(/(\d{4})/);
  return m ? Number(m[1]) : null;
}

function inRange(periodo: string | undefined, de?: string, ate?: string): boolean {
  if (!de && !ate) return true;
  const y = yearOf(periodo);
  if (y == null) return true;
  if (de && y < Number(de)) return false;
  if (ate && y > Number(ate)) return false;
  return true;
}

/** Classifica aresta → domínio semântico. */
export function classifyDomain(edgeTipo: string, otherTipo?: string): DomainKey {
  const t = (edgeTipo || "").toLowerCase();
  const ot = (otherTipo || "").toLowerCase();

  if (
    t.includes("caso") ||
    t.includes("participou") ||
    t.includes("investig") ||
    t.includes("denuncia") ||
    t.includes("indicia") ||
    ot === "caso" ||
    ot === "operacao" ||
    ot === "faccao"
  ) {
    return "justica";
  }
  if (
    t.includes("emenda") ||
    t.includes("despesa") ||
    t.includes("campanha") ||
    t.includes("doacao") ||
    t.includes("doação") ||
    t.includes("pagamento") ||
    t.includes("transferenc") ||
    t.includes("bem") ||
    t.includes("financ")
  ) {
    return "dinheiro";
  }
  if (
    t.includes("contrato") ||
    t.includes("licitacao") ||
    t.includes("licitação") ||
    t.includes("fornecid") ||
    t.includes("socio") ||
    t.includes("sócio") ||
    t.includes("cnpj") ||
    ot === "empresa" ||
    ot === "contrato" ||
    ot === "licitacao"
  ) {
    return "empresas";
  }
  // política: partido, mandato, cargo, proposição, frentes
  return "politica";
}

function subtypeOf(edgeTipo: string, otherTipo?: string): string {
  const t = (edgeTipo || "").toLowerCase();
  const ot = (otherTipo || "").toLowerCase();
  if (t.includes("emenda")) return "emenda";
  if (t.includes("campanha")) return "campanha";
  if (t.includes("despesa_parlamentar") || t.includes("despesa")) return "despesa";
  if (t.includes("transferenc") || t.includes("beneficiou")) return "transferencia";
  if (t.includes("contrato") || ot === "contrato") return "contrato";
  if (t.includes("licit") || ot === "licitacao") return "licitacao";
  if (t.includes("filiad") || ot === "partido") return "partido";
  if (t.includes("mandato") || t.includes("cargo") || ot === "mandato" || ot === "estado")
    return "mandato";
  if (t.includes("proposic") || ot === "proposicao") return "proposicao";
  if (t.includes("membro") || ot === "instituicao") return "frente";
  if (ot === "caso" || t.includes("participou")) return "caso";
  if (ot === "empresa") return "empresa";
  return "outros";
}

type NeighborHit = {
  node: GraphNode;
  edge: GraphEdge;
  domain: DomainKey;
  subtype: string;
};

function egoHits(
  focal: string,
  filters?: { de?: string; ate?: string }
): NeighborHit[] {
  const { nodes, edges } = loadGraph();
  const hits: NeighborHit[] = [];
  for (const e of edges) {
    if (e.from !== focal && e.to !== focal) continue;
    if (!inRange(e.periodo, filters?.de, filters?.ate)) continue;
    const otherId = e.from === focal ? e.to : e.from;
    const n = nodes.get(otherId);
    if (!n) continue;
    const domain = classifyDomain(e.tipo, n.tipo);
    hits.push({
      node: n,
      edge: e,
      domain,
      subtype: subtypeOf(e.tipo, n.tipo),
    });
  }
  return hits;
}

function domainCounts(hits: NeighborHit[]): Record<DomainKey, number> {
  const c: Record<DomainKey, number> = {
    politica: 0,
    dinheiro: 0,
    empresas: 0,
    justica: 0,
  };
  for (const h of hits) c[h.domain] += 1;
  return c;
}

/**
 * Diversified top-k: não deixa um subtype dominar o canvas.
 * Quotas tipicas da spec §70.
 */
export function diversifiedTopK(
  hits: NeighborHit[],
  maxLeaves: number,
  quotas?: Record<string, number>
): { kept: NeighborHit[]; overflow: NeighborHit[] } {
  const q =
    quotas ||
    ({
      emenda: 3,
      campanha: 3,
      despesa: 3,
      transferencia: 2,
      contrato: 2,
      licitacao: 2,
      partido: 2,
      mandato: 3,
      proposicao: 2,
      frente: 2,
      caso: 3,
      empresa: 3,
      outros: 2,
    } as Record<string, number>);

  const bySub = new Map<string, NeighborHit[]>();
  for (const h of hits) {
    const list = bySub.get(h.subtype) || [];
    list.push(h);
    bySub.set(h.subtype, list);
  }
  // grau implícito: manter ordem de entrada (já filtrada)

  const kept: NeighborHit[] = [];
  const usedIds = new Set<string>();
  const take = (sub: string, n: number) => {
    const list = bySub.get(sub) || [];
    let got = 0;
    for (const h of list) {
      if (got >= n || kept.length >= maxLeaves) break;
      if (usedIds.has(h.node.id)) continue;
      usedIds.add(h.node.id);
      kept.push(h);
      got += 1;
    }
  };

  for (const [sub, n] of Object.entries(q)) take(sub, n);
  // completar com restantes se ainda houver vaga
  if (kept.length < maxLeaves) {
    for (const h of hits) {
      if (kept.length >= maxLeaves) break;
      if (usedIds.has(h.node.id)) continue;
      usedIds.add(h.node.id);
      kept.push(h);
    }
  }

  const overflow = hits.filter((h) => !usedIds.has(h.node.id));
  return { kept, overflow };
}

function supernodeId(focal: string, domain: DomainKey, subtype?: string): string {
  // Separador :: evita colisão com ids p_cam_ / p_tse_
  return subtype
    ? `sn::${domain}::${subtype}::${focal}`
    : `sn::${domain}::${focal}`;
}

function makeSupernode(
  id: string,
  label: string,
  count: number
): GraphNode {
  return {
    id,
    nome: `[${label} · ${count}]`,
    tipo: "supernode",
  };
}

function buildResumo(
  focal: string,
  center: GraphNode,
  hits: NeighborHit[],
  counts: Record<DomainKey, number>
): VisualGraphResult {
  const nodes: GraphNode[] = [center];
  const edges: GraphEdge[] = [];
  const supernodes: GraphNode[] = [];
  const expandable: ExpandableGroup[] = [];
  const reason_codes = ["semantic_resumo", "domain_supernodes"];

  (Object.keys(DOMAIN_LABEL) as DomainKey[]).forEach((dom) => {
    const n = counts[dom];
    if (!n) return;
    const sid = supernodeId(focal, dom);
    const sn = makeSupernode(sid, DOMAIN_LABEL[dom], n);
    nodes.push(sn);
    supernodes.push(sn);
    edges.push({
      id: `e_${focal}_${sid}`,
      from: focal,
      to: sid,
      tipo: `agrega_${dom}`,
      contexto: `${n} relações no domínio ${DOMAIN_LABEL[dom]}`,
      justificativa_documental:
        "Supernó de domínio (FASE 8): clique para zoom semântico. Não é acusação.",
      grau_confirmacao: "fato_documentado",
    });
    expandable.push({
      id: sid,
      domain: dom,
      label: DOMAIN_LABEL[dom],
      count: n,
      mode: dom,
    });
  });

  return {
    focal,
    mode: "resumo",
    expand: null,
    nodes,
    edges,
    supernodes,
    expandable_groups: expandable,
    domain_counts: counts,
    hidden_count: hits.length,
    reason_codes,
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria",
  };
}

function buildDomainView(
  focal: string,
  center: GraphNode,
  hits: NeighborHit[],
  mode: DomainKey,
  expand: string | null,
  maxLeaves: number
): VisualGraphResult {
  let pool = hits.filter((h) => h.domain === mode);
  if (expand) {
    pool = pool.filter((h) => h.subtype === expand);
  }

  const { kept, overflow } = diversifiedTopK(pool, maxLeaves);
  const nodes: GraphNode[] = [center];
  const edges: GraphEdge[] = [];
  const seenEdge = new Set<string>();
  const supernodes: GraphNode[] = [];
  const expandable: ExpandableGroup[] = [];

  for (const h of kept) {
    if (!nodes.find((n) => n.id === h.node.id)) nodes.push(h.node);
    if (!seenEdge.has(h.edge.id)) {
      seenEdge.add(h.edge.id);
      edges.push(h.edge);
    }
  }

  // Sub-supernós por subtype no overflow (quando não expandiu um subtype)
  if (!expand && overflow.length) {
    const bySub = new Map<string, number>();
    for (const h of overflow) {
      bySub.set(h.subtype, (bySub.get(h.subtype) || 0) + 1);
    }
    bySub.forEach((count, sub) => {
      if (count < 2) return;
      const sid = supernodeId(focal, mode, sub);
      const label = SUBTYPE_LABEL[sub] || sub.toUpperCase();
      const sn = makeSupernode(sid, label, count);
      nodes.push(sn);
      supernodes.push(sn);
      edges.push({
        id: `e_${focal}_${sid}`,
        from: focal,
        to: sid,
        tipo: `agrega_${mode}_${sub}`,
        contexto: `${count} omitidos no canvas — ver lista/tabela`,
        justificativa_documental:
          "Supernó de UI (diversified top-k). Expandir ou abrir lista.",
        grau_confirmacao: "fato_documentado",
      });
      expandable.push({
        id: sid,
        domain: mode,
        subtype: sub,
        label,
        count,
        mode,
        expand: sub,
      });
    });
  }

  // Voltar aos domínios irmãos como chips (não no canvas se mode focado)
  const allCounts = domainCounts(hits);

  return {
    focal,
    mode,
    expand,
    nodes,
    edges,
    supernodes,
    expandable_groups: expandable,
    domain_counts: allCounts,
    hidden_count: overflow.length,
    reason_codes: [
      "semantic_zoom",
      "diversified_top_k",
      expand ? `expand_${expand}` : `mode_${mode}`,
    ],
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria",
  };
}

/**
 * Entrada principal do VISUAL_GRAPH_SERVICE (spec §77).
 */
export function visualGraph(opts: {
  focal: string;
  mode?: GraphMode | string;
  expand?: string | null;
  max_nodes?: number;
  de?: string;
  ate?: string;
}): VisualGraphResult {
  const mode = (opts.mode || "resumo") as GraphMode;
  const expand = opts.expand || null;
  const maxNodes = Math.min(
    opts.max_nodes ?? GRAPH_LIMITS.initial_nodes,
    GRAPH_LIMITS.hard_nodes
  );
  const { nodes } = loadGraph();
  const center = nodes.get(opts.focal) || {
    id: opts.focal,
    nome: opts.focal,
    tipo: "pessoa",
  };
  const hits = egoHits(opts.focal, { de: opts.de, ate: opts.ate });
  const counts = domainCounts(hits);

  if (mode === "resumo") {
    return buildResumo(opts.focal, center, hits, counts);
  }

  if (
    mode === "politica" ||
    mode === "dinheiro" ||
    mode === "empresas" ||
    mode === "justica"
  ) {
    return buildDomainView(
      opts.focal,
      center,
      hits,
      mode,
      expand,
      Math.max(8, maxNodes - 6)
    );
  }

  // completo: k-hop + cap clássico
  const raw = subgraph(opts.focal, 1, { de: opts.de, ate: opts.ate });
  const capped = capSubgraph(raw, { maxNodes, maxEdges: GRAPH_LIMITS.hard_edges });
  return {
    focal: opts.focal,
    mode: "completo",
    expand: null,
    nodes: capped.nodes,
    edges: capped.edges,
    supernodes: capped.nodes.filter((n) => n.tipo === "grupo"),
    expandable_groups: [],
    domain_counts: counts,
    hidden_count: capped.hidden_count || 0,
    reason_codes: ["completo", capped.capped ? "capped" : "uncapped"],
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria",
  };
}

/** Resolve clique em supernó → query params. */
export function parseSupernodeHref(
  supernodeIdStr: string
): { centro: string; modo: GraphMode; expand?: string } | null {
  const parts = supernodeIdStr.split("::");
  if (parts[0] !== "sn" || parts.length < 3) return null;
  const domain = parts[1] as DomainKey;
  if (!DOMAIN_LABEL[domain]) return null;
  if (parts.length === 3) {
    return { centro: parts[2], modo: domain };
  }
  if (parts.length >= 4) {
    return { centro: parts.slice(3).join("::"), modo: domain, expand: parts[2] };
  }
  return null;
}
