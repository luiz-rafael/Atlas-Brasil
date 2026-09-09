/**
 * Análise de redes (pontos_centrais.md §§9–14, 36).
 * Métricas estruturais — NÃO equivalem a poder, culpa ou influência ilícita.
 */

import "server-only";
import { loadGraph, type GraphNode, type GraphEdge } from "./graph-engine";

export const METRIC_DISCLAIMER =
  "Centralidade é uma medida estrutural da posição de uma entidade na rede. Ela não representa, isoladamente, poder político, influência ilícita ou responsabilidade criminal.";

export type MetricsOpts = {
  de?: string;
  ate?: string;
  tipos?: string[];
  graus?: string[]; // grau_confirmacao filter
};

function yearOf(periodo?: string): number | null {
  if (!periodo) return null;
  const m = periodo.match(/(\d{4})/);
  return m ? Number(m[1]) : null;
}

function edgeOk(e: GraphEdge, opts?: MetricsOpts): boolean {
  if (opts?.tipos?.length && opts.tipos.indexOf(e.tipo) < 0) return false;
  if (opts?.graus?.length) {
    const g = e.grau_confirmacao || "";
    if (opts.graus.indexOf(g) < 0) return false;
  }
  if (opts?.de || opts?.ate) {
    const y = yearOf(e.periodo);
    if (y != null) {
      if (opts.de && y < Number(opts.de)) return false;
      if (opts.ate && y > Number(opts.ate)) return false;
    }
  }
  return true;
}

function filteredGraph(opts?: MetricsOpts) {
  const { nodes, edges } = loadGraph();
  const kept = edges.filter((e) => edgeOk(e, opts));
  const deg = new Map<string, number>();
  const adj = new Map<string, string[]>();
  const add = (a: string, b: string) => {
    const la = adj.get(a) || [];
    if (la.indexOf(b) < 0) la.push(b);
    adj.set(a, la);
  };
  for (const e of kept) {
    deg.set(e.from, (deg.get(e.from) || 0) + 1);
    deg.set(e.to, (deg.get(e.to) || 0) + 1);
    add(e.from, e.to);
    add(e.to, e.from);
  }
  // só nós com grau > 0 (participam da rede filtrada)
  const active = new Map<string, GraphNode>();
  nodes.forEach((n, id) => {
    if ((deg.get(id) || 0) > 0) active.set(id, n);
  });
  return { nodes: active, edges: kept, adj, deg };
}

function bfsDistances(adj: Map<string, string[]>, start: string): Map<string, number> {
  const dist = new Map<string, number>();
  dist.set(start, 0);
  const q = [start];
  while (q.length) {
    const u = q.shift()!;
    const du = dist.get(u)!;
    const neigh = adj.get(u) || [];
    for (let i = 0; i < neigh.length; i++) {
      const v = neigh[i];
      if (!dist.has(v)) {
        dist.set(v, du + 1);
        q.push(v);
      }
    }
  }
  return dist;
}

/** Degree centrality (normalizada pelo máx. possível n-1). */
export function degreeCentrality(opts?: MetricsOpts) {
  const { nodes, deg } = filteredGraph(opts);
  const n = Math.max(1, nodes.size - 1);
  const scores: { id: string; score: number; raw: number; node: GraphNode }[] = [];
  nodes.forEach((node, id) => {
    const raw = deg.get(id) || 0;
    scores.push({ id, score: raw / n, raw, node });
  });
  scores.sort((a, b) => b.score - a.score);
  return scores;
}

/** Betweenness (Brandes, grafo não-dirigido). */
export function betweennessCentrality(opts?: MetricsOpts) {
  const { nodes, adj } = filteredGraph(opts);
  const ids: string[] = [];
  nodes.forEach((_, id) => ids.push(id));
  const cb = new Map<string, number>();
  ids.forEach((id) => cb.set(id, 0));

  for (let si = 0; si < ids.length; si++) {
    const s = ids[si];
    const stack: string[] = [];
    const pred = new Map<string, string[]>();
    const sigma = new Map<string, number>();
    const dist = new Map<string, number>();
    ids.forEach((v) => {
      pred.set(v, []);
      sigma.set(v, 0);
      dist.set(v, -1);
    });
    sigma.set(s, 1);
    dist.set(s, 0);
    const q = [s];
    while (q.length) {
      const v = q.shift()!;
      stack.push(v);
      const neigh = adj.get(v) || [];
      for (let i = 0; i < neigh.length; i++) {
        const w = neigh[i];
        if (dist.get(w)! < 0) {
          dist.set(w, dist.get(v)! + 1);
          q.push(w);
        }
        if (dist.get(w) === dist.get(v)! + 1) {
          sigma.set(w, sigma.get(w)! + sigma.get(v)!);
          pred.get(w)!.push(v);
        }
      }
    }
    const delta = new Map<string, number>();
    ids.forEach((v) => delta.set(v, 0));
    while (stack.length) {
      const w = stack.pop()!;
      const ps = pred.get(w) || [];
      for (let i = 0; i < ps.length; i++) {
        const v = ps[i];
        const c =
          (sigma.get(v)! / Math.max(1e-12, sigma.get(w)!)) *
          (1 + delta.get(w)!);
        delta.set(v, delta.get(v)! + c);
      }
      if (w !== s) cb.set(w, cb.get(w)! + delta.get(w)!);
    }
  }

  // undirected: divide by 2
  const scores: { id: string; score: number; raw: number; node: GraphNode }[] = [];
  const norm = Math.max(1, (ids.length - 1) * (ids.length - 2));
  ids.forEach((id) => {
    const raw = (cb.get(id) || 0) / 2;
    scores.push({
      id,
      raw,
      score: raw / norm,
      node: nodes.get(id)!,
    });
  });
  scores.sort((a, b) => b.score - a.score);
  return scores;
}

/** Closeness: 1 / average distance (component). */
export function closenessCentrality(opts?: MetricsOpts) {
  const { nodes, adj } = filteredGraph(opts);
  const scores: { id: string; score: number; raw: number; node: GraphNode }[] = [];
  nodes.forEach((node, id) => {
    const dist = bfsDistances(adj, id);
    let sum = 0;
    let reach = 0;
    dist.forEach((d) => {
      if (d > 0) {
        sum += d;
        reach += 1;
      }
    });
    const raw = sum > 0 ? reach / sum : 0;
    const score = nodes.size > 1 ? raw : 0;
    scores.push({ id, score, raw, node });
  });
  scores.sort((a, b) => b.score - a.score);
  return scores;
}

/** Eigenvector via power iteration. */
export function eigenvectorCentrality(opts?: MetricsOpts, iters = 40) {
  const { nodes, adj } = filteredGraph(opts);
  const ids: string[] = [];
  nodes.forEach((_, id) => ids.push(id));
  if (!ids.length) return [];
  const x = new Map<string, number>();
  ids.forEach((id) => x.set(id, 1));
  for (let t = 0; t < iters; t++) {
    const y = new Map<string, number>();
    let norm = 0;
    ids.forEach((id) => {
      let s = 0;
      const neigh = adj.get(id) || [];
      for (let i = 0; i < neigh.length; i++) s += x.get(neigh[i]) || 0;
      y.set(id, s);
      norm += s * s;
    });
    norm = Math.sqrt(norm) || 1;
    ids.forEach((id) => x.set(id, (y.get(id) || 0) / norm));
  }
  const scores = ids.map((id) => ({
    id,
    score: x.get(id) || 0,
    raw: x.get(id) || 0,
    node: nodes.get(id)!,
  }));
  scores.sort((a, b) => b.score - a.score);
  return scores;
}

export type MetricName = "degree" | "betweenness" | "closeness" | "eigenvector";

export function hubsRanking(
  metric: MetricName = "degree",
  opts?: MetricsOpts & { tipo?: string; limit?: number }
) {
  let scores;
  if (metric === "betweenness") scores = betweennessCentrality(opts);
  else if (metric === "closeness") scores = closenessCentrality(opts);
  else if (metric === "eigenvector") scores = eigenvectorCentrality(opts);
  else scores = degreeCentrality(opts);

  if (opts?.tipo && opts.tipo !== "todos") {
    scores = scores.filter((s) => s.node.tipo === opts.tipo);
  }
  const limit = opts?.limit || 25;
  return {
    metric,
    disclaimer: METRIC_DISCLAIMER,
    ranking: scores.slice(0, limit).map((s, i) => ({
      rank: i + 1,
      id: s.id,
      nome: s.node.nome,
      tipo: s.node.tipo,
      score: Number(s.score.toFixed(6)),
      raw: s.raw,
    })),
  };
}

/** Label propagation — comunidades. */
export function detectCommunities(opts?: MetricsOpts, maxIter = 30) {
  const { nodes, adj } = filteredGraph(opts);
  const labels = new Map<string, string>();
  nodes.forEach((_, id) => labels.set(id, id));
  const ids: string[] = [];
  nodes.forEach((_, id) => ids.push(id));

  for (let t = 0; t < maxIter; t++) {
    let changed = 0;
    // ordem estável (determinística) por id
    ids.sort();
    for (let i = 0; i < ids.length; i++) {
      const u = ids[i];
      const neigh = adj.get(u) || [];
      if (!neigh.length) continue;
      const counts = new Map<string, number>();
      for (let k = 0; k < neigh.length; k++) {
        const lab = labels.get(neigh[k])!;
        counts.set(lab, (counts.get(lab) || 0) + 1);
      }
      let best = labels.get(u)!;
      let bestC = -1;
      counts.forEach((c, lab) => {
        if (c > bestC || (c === bestC && lab < best)) {
          bestC = c;
          best = lab;
        }
      });
      if (best !== labels.get(u)) {
        labels.set(u, best);
        changed += 1;
      }
    }
    if (!changed) break;
  }

  const groups = new Map<string, string[]>();
  labels.forEach((lab, id) => {
    const g = groups.get(lab) || [];
    g.push(id);
    groups.set(lab, g);
  });

  const communities: {
    id: string;
    size: number;
    membros: { id: string; nome: string; tipo: string }[];
  }[] = [];
  let i = 0;
  groups.forEach((memberIds) => {
    if (memberIds.length < 2) return;
    i += 1;
    communities.push({
      id: `com_${i}`,
      size: memberIds.length,
      membros: memberIds.map((id) => {
        const n = nodes.get(id)!;
        return { id, nome: n.nome, tipo: n.tipo };
      }),
    });
  });
  communities.sort((a, b) => b.size - a.size);

  const labelObj: Record<string, string> = {};
  labels.forEach((lab, id) => {
    labelObj[id] = lab;
  });

  return {
    disclaimer: METRIC_DISCLAIMER,
    communities,
    labels: labelObj,
  };
}

/** Pontes: alta betweenness entre comunidades distintas. */
export function findBridges(opts?: MetricsOpts, limit = 15) {
  const { communities, labels } = detectCommunities(opts);
  const bet = betweennessCentrality(opts);
  const labelOf = (id: string) => labels[id] || id;

  const bridges = bet
    .filter((s) => {
      // vizinhos em >1 comunidade
      const { adj } = filteredGraph(opts);
      const neigh = adj.get(s.id) || [];
      const labs = new Set<string>();
      neigh.forEach((v) => labs.add(labelOf(v)));
      labs.add(labelOf(s.id));
      return labs.size >= 2 && (s.raw > 0 || neigh.length >= 2);
    })
    .slice(0, limit)
    .map((s, i) => ({
      rank: i + 1,
      id: s.id,
      nome: s.node.nome,
      tipo: s.node.tipo,
      betweenness: Number(s.score.toFixed(6)),
      comunidade: labelOf(s.id),
    }));

  return {
    disclaimer:
      METRIC_DISCLAIMER +
      " Pontes conectam grupos estruturais; isso não implica aliança política ou ilícito.",
    bridges,
    communities_count: communities.length,
  };
}

/** Hubs por janelas temporais (pontos_centrais §12). */
export function hubsByPeriod(
  metric: MetricName = "degree",
  windows?: { de: string; ate: string; label: string }[]
) {
  const wins =
    windows ||
    [
      { de: "1985", ate: "1994", label: "1985–1994" },
      { de: "1995", ate: "2002", label: "1995–2002" },
      { de: "2003", ate: "2010", label: "2003–2010" },
      { de: "2011", ate: "2018", label: "2011–2018" },
      { de: "2019", ate: "2026", label: "2019–2026" },
    ];
  return {
    metric,
    disclaimer: METRIC_DISCLAIMER,
    periodos: wins.map((w) => ({
      ...w,
      hubs: hubsRanking(metric, { de: w.de, ate: w.ate, limit: 5 }).ranking,
    })),
  };
}
