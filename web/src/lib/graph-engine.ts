/**
 * Motor de grafo em memória (fallback / complemento ao Neo4j).
 * Paths, k-hop e pontos de encontro — regra: path ≠ culpa.
 */

import "server-only";
import { getKB, type Entidade, type Documento } from "./kb";

export type GraphNode = {
  id: string;
  nome: string;
  tipo: string;
  partido?: string | null;
  cargo_atual?: string | null;
};

export type GraphEdge = {
  id: string;
  from: string;
  to: string;
  tipo: string;
  periodo?: string;
  contexto?: string;
  justificativa_documental?: string;
  grau_confirmacao?: string;
  caso_id?: string | null;
  fonte_ids?: string[];
  fontes?: string[];
};

export const PATH_DISCLAIMER =
  "Compartilhar um nó ou caminho no grafo não significa compartilhar responsabilidade, culpa ou conduta ilícita. O Atlas documenta relações; não acusa.";

type Adj = Map<string, GraphEdge[]>;

let _cachedGraph: {
  nodes: Map<string, GraphNode>;
  edges: GraphEdge[];
} | null = null;

function buildAdj(edges: GraphEdge[]): Adj {
  const adj: Adj = new Map();
  const add = (id: string, e: GraphEdge) => {
    const list = adj.get(id) || [];
    list.push(e);
    adj.set(id, list);
  };
  for (const e of edges) {
    add(e.from, e);
    add(e.to, e);
  }
  return adj;
}

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

export function loadGraph(opts?: {
  includeParticipacoes?: boolean;
  hideIsoladas?: boolean;
}): { nodes: Map<string, GraphNode>; edges: GraphEdge[] } {
  const hide = opts?.hideIsoladas !== false;
  const withPart = opts?.includeParticipacoes !== false;
  // Cache do grafo padrão (caminho quente: perfil / macro).
  if (hide && withPart && _cachedGraph) {
    return _cachedGraph;
  }

  const kb = getKB();
  const nodes = new Map<string, GraphNode>();

  for (const e of kb.entidades) {
    if (hide && e.isolada) continue;
    nodes.set(e.id, {
      id: e.id,
      nome: e.nome,
      tipo: e.tipo,
      partido: e.partido,
      cargo_atual: e.cargo_atual,
    });
  }
  for (const c of kb.casos) {
    nodes.set(c.id, { id: c.id, nome: c.nome, tipo: "caso" });
  }
  // Documentos ficam fora do grafo de caminhos (só via fonte_ids nas arestas)

  const edges: GraphEdge[] = [];
  for (const r of kb.relacoes) {
    if (!nodes.has(r.origem) || !nodes.has(r.destino)) continue;
    edges.push({
      id: r.id,
      from: r.origem,
      to: r.destino,
      tipo: r.tipo,
      periodo: r.periodo,
      contexto: r.contexto,
      justificativa_documental: r.justificativa_documental,
      grau_confirmacao: r.grau_confirmacao,
      caso_id: r.caso_id,
      fonte_ids: r.fonte_ids || [],
      fontes: r.fontes,
    });
  }

  if (withPart) {
    for (const rpc of kb.registros_pessoa_caso) {
      if (!nodes.has(rpc.pessoa_id) || !nodes.has(rpc.caso_id)) continue;
      edges.push({
        id: rpc.id,
        from: rpc.pessoa_id,
        to: rpc.caso_id,
        tipo: "participou_de",
        contexto: rpc.acusacao,
        grau_confirmacao: rpc.camada,
        caso_id: rpc.caso_id,
        fonte_ids: (rpc as { fonte_ids?: string[] }).fonte_ids || [],
        fontes: rpc.fontes,
      });
    }
  }

  const out = { nodes, edges };
  if (hide && withPart) _cachedGraph = out;
  return out;
}

/** Limites UI — grafo completo fica na máquina (melhoria_ux §§25–26). */
export const GRAPH_LIMITS = {
  initial_nodes: 25,
  soft_nodes: 50,
  hard_nodes: 100,
  hard_edges: 150,
  macro_hubs: 20,
} as const;

const SUPER_LABEL: Record<string, string> = {
  pessoa: "PESSOAS",
  empresa: "EMPRESAS",
  partido: "PARTIDOS",
  instituicao: "INSTITUIÇÕES",
  caso: "CASOS",
  documento: "DOCUMENTOS",
  faccao: "FACÇÕES",
  operacao: "OPERAÇÕES",
};

export function subgraph(
  centroId: string,
  profundidade = 1,
  filters?: { de?: string; ate?: string; tipos?: string[] }
) {
  const { nodes, edges } = loadGraph();
  const adj = buildAdj(edges);
  const keptNodes = new Set<string>([centroId]);
  const keptEdges: GraphEdge[] = [];
  let frontier = [centroId];

  for (let d = 0; d < profundidade; d++) {
    const next: string[] = [];
    for (let fi = 0; fi < frontier.length; fi++) {
      const id = frontier[fi];
      const neighbors = adj.get(id) || [];
      for (let ei = 0; ei < neighbors.length; ei++) {
        const e = neighbors[ei];
        if (filters?.tipos?.length && filters.tipos.indexOf(e.tipo) < 0) continue;
        if (!inRange(e.periodo, filters?.de, filters?.ate)) continue;
        const other = e.from === id ? e.to : e.from;
        if (!keptEdges.find((x) => x.id === e.id)) keptEdges.push(e);
        if (!keptNodes.has(other)) {
          keptNodes.add(other);
          next.push(other);
        }
      }
    }
    frontier = next;
  }

  const nodeList: GraphNode[] = [];
  keptNodes.forEach((id) => {
    const n = nodes.get(id);
    if (n) nodeList.push(n);
  });

  return {
    centro: centroId,
    profundidade,
    nodes: nodeList,
    edges: keptEdges,
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria" as const,
  };
}

/** Grafo induzido por um conjunto de IDs (visão macro hubs). */
export function inducedSubgraph(ids: string[]) {
  const keep = new Set(ids);
  const { nodes, edges } = loadGraph();
  const nodeList: GraphNode[] = [];
  keep.forEach((id) => {
    const n = nodes.get(id);
    if (n) nodeList.push(n);
  });
  const edgeList = edges.filter((e) => keep.has(e.from) && keep.has(e.to));
  return {
    nodes: nodeList,
    edges: edgeList,
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria" as const,
  };
}

/**
 * Corta ego-subgrafo ao teto; excedente vira supernós por tipo ([EMPRESAS · N]).
 */
export function capSubgraph(
  data: {
    centro: string;
    profundidade: number;
    nodes: GraphNode[];
    edges: GraphEdge[];
  },
  opts?: { maxNodes?: number; maxEdges?: number }
) {
  const maxNodes = Math.min(
    opts?.maxNodes ?? GRAPH_LIMITS.hard_nodes,
    GRAPH_LIMITS.hard_nodes
  );
  const maxEdges = Math.min(
    opts?.maxEdges ?? GRAPH_LIMITS.hard_edges,
    GRAPH_LIMITS.hard_edges
  );
  const centro = data.centro;
  const deg = new Map<string, number>();
  for (const e of data.edges) {
    deg.set(e.from, (deg.get(e.from) || 0) + 1);
    deg.set(e.to, (deg.get(e.to) || 0) + 1);
  }

  const others = data.nodes
    .filter((n) => n.id !== centro)
    .sort((a, b) => (deg.get(b.id) || 0) - (deg.get(a.id) || 0));

  if (data.nodes.length <= maxNodes && data.edges.length <= maxEdges) {
    return {
      ...data,
      nodes: data.nodes,
      edges: data.edges,
      capped: false,
      hidden_count: 0,
      disclaimer: PATH_DISCLAIMER,
      motor: "memoria" as const,
    };
  }

  // reserva slots para supernós (até 1 por tipo)
  const reserve = 8;
  const keepBudget = Math.max(2, maxNodes - reserve);
  const keepIds = new Set<string>([centro]);
  for (const n of others) {
    if (keepIds.size >= keepBudget) break;
    keepIds.add(n.id);
  }

  const overflow = others.filter((n) => !keepIds.has(n.id));
  const byTipo = new Map<string, GraphNode[]>();
  for (const n of overflow) {
    const t = n.tipo || "outros";
    const list = byTipo.get(t) || [];
    list.push(n);
    byTipo.set(t, list);
  }

  const nodes: GraphNode[] = data.nodes.filter((n) => keepIds.has(n.id));
  const superEdges: GraphEdge[] = [];
  byTipo.forEach((list, tipo) => {
    if (!list.length) return;
    const label = SUPER_LABEL[tipo] || tipo.toUpperCase();
    const sid = `grp_${tipo}_${centro}`;
    nodes.push({
      id: sid,
      nome: `[${label} · ${list.length}]`,
      tipo: "grupo",
    });
    keepIds.add(sid);
    superEdges.push({
      id: `e_${centro}_${sid}_grupo`,
      from: centro,
      to: sid,
      tipo: "agrupado",
      contexto: `${list.length} entidades do tipo ${tipo} omitidas no canvas`,
      justificativa_documental:
        "Supernó de UI: relações individuais existem na KB; clique Expandir/aumentar limite para detalhar.",
      grau_confirmacao: "fato_documentado",
    });
  });

  let edges = data.edges.filter((e) => keepIds.has(e.from) && keepIds.has(e.to));
  edges = edges.concat(superEdges);
  if (edges.length > maxEdges) {
    const centroEdges = edges.filter((e) => e.from === centro || e.to === centro);
    const rest = edges.filter((e) => e.from !== centro && e.to !== centro);
    edges = centroEdges.concat(rest).slice(0, maxEdges);
  }

  return {
    ...data,
    nodes,
    edges,
    capped: true,
    hidden_count: overflow.length,
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria" as const,
  };
}

function edgeBetween(adj: Adj, u: string, v: string): GraphEdge | undefined {
  const list = adj.get(u) || [];
  for (let i = 0; i < list.length; i++) {
    const x = list[i];
    if ((x.from === u && x.to === v) || (x.from === v && x.to === u)) return x;
  }
  return undefined;
}

export function shortestPath(a: string, b: string, max = 6) {
  const { nodes, edges } = loadGraph();
  if (!nodes.has(a) || !nodes.has(b)) {
    return { found: false as const, paths: [], disclaimer: PATH_DISCLAIMER };
  }
  const adj = buildAdj(edges);
  const queue: string[][] = [[a]];
  const visited = new Set<string>([a]);
  const paths: { node_ids: string[]; edge_ids: string[]; edges: GraphEdge[] }[] =
    [];

  while (queue.length) {
    const path = queue.shift()!;
    const last = path[path.length - 1];
    if (path.length - 1 > max) continue;
    if (last === b && path.length > 1) {
      const edgeList: GraphEdge[] = [];
      for (let i = 0; i < path.length - 1; i++) {
        const e = edgeBetween(adj, path[i], path[i + 1]);
        if (e) edgeList.push(e);
      }
      paths.push({
        node_ids: path,
        edge_ids: edgeList.map((e) => e.id),
        edges: edgeList,
      });
      if (paths.length >= 3) break;
      continue;
    }
    const neighbors = adj.get(last) || [];
    for (let i = 0; i < neighbors.length; i++) {
      const e = neighbors[i];
      const other = e.from === last ? e.to : e.from;
      if (visited.has(other) && other !== b) continue;
      if (path.indexOf(other) >= 0) continue;
      visited.add(other);
      queue.push(path.concat([other]));
    }
  }

  const labeled = paths.map((p) => {
    const tiposMap: Record<string, boolean> = {};
    p.edges.forEach((e) => {
      tiposMap[e.tipo] = true;
    });
    return {
      ...p,
      nos: p.node_ids.map((id) => nodes.get(id)!).filter(Boolean),
      resumo: {
        nos: p.node_ids.length,
        relacoes: p.edges.length,
        tipos: Object.keys(tiposMap),
      },
    };
  });

  return {
    found: labeled.length > 0,
    a,
    b,
    paths: labeled,
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria" as const,
  };
}

export function meetingPoints(a: string, b: string, egoDepth = 2) {
  const { nodes, edges } = loadGraph();
  const adj = buildAdj(edges);

  function ego(center: string): Set<string> {
    const set = new Set<string>([center]);
    let frontier = [center];
    for (let d = 0; d < egoDepth; d++) {
      const next: string[] = [];
      for (let fi = 0; fi < frontier.length; fi++) {
        const id = frontier[fi];
        const neighbors = adj.get(id) || [];
        for (let ei = 0; ei < neighbors.length; ei++) {
          const e = neighbors[ei];
          const other = e.from === id ? e.to : e.from;
          if (!set.has(other)) {
            set.add(other);
            next.push(other);
          }
        }
      }
      frontier = next;
    }
    return set;
  }

  const ea = ego(a);
  const eb = ego(b);
  const inter: string[] = [];
  ea.forEach((id) => {
    if (eb.has(id) && id !== a && id !== b) inter.push(id);
  });

  const byTipo: Record<string, GraphNode[]> = {};
  for (let i = 0; i < inter.length; i++) {
    const n = nodes.get(inter[i]);
    if (!n) continue;
    const t = n.tipo || "outro";
    if (!byTipo[t]) byTipo[t] = [];
    byTipo[t].push(n);
  }

  return {
    a,
    b,
    pontos: byTipo,
    total: inter.length,
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria" as const,
  };
}

export function whyConnected(a: string, b: string) {
  const { edges } = loadGraph();
  const diretas = edges.filter(
    (e) =>
      (e.from === a && e.to === b) || (e.from === b && e.to === a)
  );
  const path = shortestPath(a, b, 5);
  return {
    a,
    b,
    diretas,
    caminhos: path.paths.slice(0, 3),
    disclaimer: PATH_DISCLAIMER,
    motor: "memoria" as const,
  };
}

export function macroClusters() {
  const { nodes, edges } = loadGraph({ includeParticipacoes: true });
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.from, (degree.get(e.from) || 0) + 1);
    degree.set(e.to, (degree.get(e.to) || 0) + 1);
  }

  const clusters: Record<string, GraphNode[]> = {
    politica: [],
    empresas: [],
    instituicoes: [],
    casos: [],
    partidos: [],
    crime_organizado: [],
    operacoes: [],
  };

  nodes.forEach((n) => {
    if ((degree.get(n.id) || 0) === 0 && n.tipo !== "caso") return;
    if (n.tipo === "pessoa") clusters.politica.push(n);
    else if (n.tipo === "empresa") clusters.empresas.push(n);
    else if (n.tipo === "instituicao") clusters.instituicoes.push(n);
    else if (n.tipo === "caso") clusters.casos.push(n);
    else if (n.tipo === "partido") clusters.partidos.push(n);
    else if (n.tipo === "faccao" || n.tipo === "organizacao_criminosa")
      clusters.crime_organizado.push(n);
    else if (n.tipo === "operacao") clusters.operacoes.push(n);
  });

  return { clusters, edge_count: edges.length, disclaimer: PATH_DISCLAIMER };
}

export function resolveDocument(id: string): Documento | undefined {
  return getKB().documentos?.find((d) => d.id === id);
}

export function buscaAvancada(q: string) {
  const s = q.trim().toLowerCase();
  const kb = getKB();
  if (!s) {
    return {
      pessoas: [],
      empresas: [],
      partidos: [],
      instituicoes: [],
      casos: [],
      documentos: [],
      faccoes: [],
      operacoes: [],
    };
  }

  type Scored = { item: Entidade | Documento | { id: string; nome: string }; score: number; tipo: string };
  const scored: Scored[] = [];

  const scoreName = (nome: string, extra: string[] = []) => {
    const n = nome.toLowerCase();
    if (n === s) return 100;
    if (n.startsWith(s)) return 80;
    if (n.includes(s)) return 60;
    for (let i = 0; i < extra.length; i++) {
      if (extra[i].toLowerCase().includes(s)) return 50;
    }
    return 0;
  };

  for (const e of kb.entidades) {
    if (e.isolada) continue;
    const sc = scoreName(e.nome, [
      e.partido || "",
      e.cargo_atual || "",
      ...(e.tags || []),
      ...(e.aliases || []),
    ]);
    if (sc > 0) scored.push({ item: e, score: sc, tipo: e.tipo });
  }
  for (const c of kb.casos) {
    const sc = scoreName(c.nome, c.eixos || []);
    if (sc > 0) scored.push({ item: c, score: sc, tipo: "caso" });
  }
  for (const d of kb.documentos || []) {
    const sc = scoreName(d.titulo, [d.orgao || "", d.tipo || ""]);
    if (sc > 0) scored.push({ item: d, score: sc, tipo: "documento" });
  }

  scored.sort((x, y) => y.score - x.score);

  const pick = (tipo: string) =>
    scored.filter((x) => x.tipo === tipo).map((x) => x.item);

  return {
    pessoas: pick("pessoa"),
    empresas: pick("empresa"),
    partidos: pick("partido"),
    instituicoes: pick("instituicao"),
    casos: pick("caso"),
    documentos: pick("documento"),
    faccoes: pick("faccao"),
    operacoes: pick("operacao"),
  };
}
