"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import InteractiveGraph, { type GEdge, type GNode } from "@/components/InteractiveGraph";

type EdgeExtra = GEdge & {
  justificativa_documental?: string;
  contexto?: string;
  periodo?: string;
};

const MAX_NODES = 30;

export default function ProfileMicroGraph({
  centro,
  nodes,
  edges,
}: {
  centro: string;
  nodes: GNode[];
  edges: EdgeExtra[];
}) {
  const { cappedNodes, cappedEdges } = useMemo(() => {
    if (nodes.length <= MAX_NODES) {
      return { cappedNodes: nodes, cappedEdges: edges };
    }
    const degree = new Map<string, number>();
    for (const e of edges) {
      degree.set(e.from, (degree.get(e.from) || 0) + 1);
      degree.set(e.to, (degree.get(e.to) || 0) + 1);
    }
    const others = nodes
      .filter((n) => n.id !== centro)
      .sort((a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0))
      .slice(0, MAX_NODES - 1);
    const keep = new Set([centro, ...others.map((n) => n.id)]);
    return {
      cappedNodes: nodes.filter((n) => keep.has(n.id)),
      cappedEdges: edges.filter((e) => keep.has(e.from) && keep.has(e.to)),
    };
  }, [nodes, edges, centro]);

  const [edgeId, setEdgeId] = useState<string | null>(
    cappedEdges[0]?.id || null
  );
  const selected = cappedEdges.find((e) => e.id === edgeId) || null;
  const byId = Object.fromEntries(cappedNodes.map((n) => [n.id, n]));

  return (
    <div className="profile-micro-graph stack">
      <p className="muted">
        Zoom semântico (FASE 8): Politica / Dinheiro / Empresas / Justiça como
        supernós. Clique para expandir — relação no grafo ≠ culpa.
      </p>
      <InteractiveGraph
        nodes={cappedNodes}
        edges={cappedEdges}
        centro={centro}
      />
      <section className="panel stack">
        <h3>Por que esta aresta</h3>
        {cappedEdges.length === 0 ? (
          <p className="muted">Sem relações neste recorte para montar o mini-grafo.</p>
        ) : (
          <>
            <div className="list-block">
              {cappedEdges.slice(0, 24).map((e) => {
                const a = byId[e.from]?.nome || e.from;
                const b = byId[e.to]?.nome || e.to;
                return (
                  <button
                    key={e.id}
                    type="button"
                    className={`list-item profile-edge-btn${
                      edgeId === e.id ? " active" : ""
                    }`}
                    onClick={() => setEdgeId(e.id)}
                  >
                    <p className="item-title">
                      {a} — {(e.tipo || "").replace(/_/g, " ")} → {b}
                    </p>
                    <p className="item-meta">{e.periodo || e.grau_confirmacao || ""}</p>
                  </button>
                );
              })}
            </div>
            {selected ? (
              <div className="profile-edge-detail">
                <p className="muted">
                  {selected.justificativa_documental ||
                    selected.contexto ||
                    "Sem justificativa documental nesta aresta."}
                </p>
                <div className="chips" style={{ marginTop: "0.75rem" }}>
                  <Link
                    className="btn-outline"
                    href={`/grafo?centro=${encodeURIComponent(centro)}&modo=resumo`}
                  >
                    Abrir resumo
                  </Link>
                  <Link
                    className="chip"
                    href={`/grafo?centro=${encodeURIComponent(centro)}&modo=dinheiro`}
                  >
                    Dinheiro
                  </Link>
                  <Link
                    className="chip"
                    href={`/grafo?centro=${encodeURIComponent(centro)}&modo=empresas`}
                  >
                    Empresas
                  </Link>
                </div>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
