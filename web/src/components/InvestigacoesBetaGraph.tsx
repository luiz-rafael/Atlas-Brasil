"use client";

import { useMemo, useState } from "react";
import InteractiveGraph, {
  type GEdge,
  type GNode,
} from "@/components/InteractiveGraph";
import { hrefForBetaNode } from "@/lib/investigacoes-beta-model";

type Props = {
  nodes: GNode[];
  edges: GEdge[];
  centro?: string;
  caseLabel?: string;
};

export default function InvestigacoesBetaGraph({
  nodes,
  edges,
  centro,
  caseLabel,
}: Props) {
  const [scope, setScope] = useState<"all" | "case">("case");

  const { viewNodes, viewEdges, viewCentro } = useMemo(() => {
    if (scope === "all" || !centro) {
      return {
        viewNodes: nodes,
        viewEdges: edges,
        viewCentro: "operation_lava_jato",
      };
    }
    const keep = new Set<string>([centro]);
    for (const e of edges) {
      if (e.from === centro || e.to === centro) {
        keep.add(e.from);
        keep.add(e.to);
      }
    }
    keep.add("operation_lava_jato");
    keep.add("stf_inq_3989");
    keep.add("org_stf");
    keep.add("org_pgr");
    keep.add("org_pf");
    const viewNodes = nodes.filter((n) => keep.has(n.id));
    const ids = new Set(viewNodes.map((n) => n.id));
    const viewEdges = edges.filter((e) => ids.has(e.from) && ids.has(e.to));
    return { viewNodes, viewEdges, viewCentro: centro };
  }, [nodes, edges, centro, scope]);

  return (
    <div className="stack inv-beta-graph">
      <div className="inv-graph-toolbar">
        <button
          type="button"
          className={`btn${scope === "case" ? " primary" : ""}`}
          onClick={() => setScope("case")}
        >
          {caseLabel || "Caso"}
        </button>
        <button
          type="button"
          className={`btn${scope === "all" ? " primary" : ""}`}
          onClick={() => setScope("all")}
        >
          Operação completa
        </button>
        <span className="faint">
          {viewNodes.length} nós · {viewEdges.length} arestas
        </span>
      </div>
      <div className="inv-graph-frame">
        <InteractiveGraph
          nodes={viewNodes}
          edges={viewEdges}
          centro={viewCentro}
          hrefForNode={hrefForBetaNode}
        />
      </div>
      <div className="inv-graph-legend muted">
        <span>operação</span>
        <span>inquérito</span>
        <span>pessoa</span>
        <span>instituição</span>
        <span>partido</span>
      </div>
    </div>
  );
}
