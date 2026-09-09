"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import cytoscape, { Core } from "cytoscape";
import {
  colorForEntity,
  colorForRelation,
  hrefForEntity,
} from "@/lib/viz-colors";

export type GNode = {
  id: string;
  nome: string;
  tipo: string;
  /** URL opcional (ex.: foto oficial) — só nós pessoa. */
  image?: string | null;
};
export type GEdge = {
  id: string;
  from: string;
  to: string;
  tipo: string;
  grau_confirmacao?: string;
};

const REL_FILTERS = [
  { id: "all", label: "Todos" },
  { id: "politico", label: "Político" },
  { id: "financeira", label: "Financeira" },
  { id: "institucional", label: "Institucional" },
  { id: "investigacao", label: "Investigação" },
  { id: "outras", label: "Outras" },
] as const;

function bucketRel(tipo: string): string {
  const c = colorForRelation(tipo);
  if (c === "#D5C7A4") return "politico";
  if (c === "#B08B44") return "financeira";
  if (c === "#55738B") return "institucional";
  if (c === "#76667F") return "investigacao";
  return "outras";
}

function shortLabel(nome: string, max = 22) {
  const t = (nome || "").trim();
  if (t.length <= max) return t;
  return t.slice(0, max - 1) + "…";
}

function destroyCy(cy: Core | null, container?: HTMLElement | null) {
  if (!cy) return;
  try {
    if (container) container.style.pointerEvents = "none";
    // Para animações/layout antes do destroy — evita notify=null no rAF
    try {
      cy.stop(true);
    } catch {
      /* ignore */
    }
    cy.removeAllListeners();
    if (!cy.destroyed()) cy.destroy();
  } catch {
    /* race destroy/hover */
  }
}

export default function InteractiveGraph({
  nodes,
  edges,
  centro,
  hrefForNode,
}: {
  nodes: GNode[];
  edges: GEdge[];
  centro?: string;
  /** Override de navegação ao abrir um nó. */
  hrefForNode?: (node: GNode) => string | null;
}) {
  const router = useRouter();
  const routerRef = useRef(router);
  routerRef.current = router;
  const hrefForNodeRef = useRef(hrefForNode);
  hrefForNodeRef.current = hrefForNode;

  const ref = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const layoutRef = useRef<{ stop?: () => void } | null>(null);
  const [relFilter, setRelFilter] = useState<string>("all");
  const [expand, setExpand] = useState(false);
  const [selected, setSelected] = useState<string | null>(centro || null);
  const [running, setRunning] = useState(false);

  const byId = useMemo(
    () => Object.fromEntries(nodes.map((n) => [n.id, n])),
    [nodes]
  );

  const visibleEdges = useMemo(() => {
    if (relFilter === "all") return edges;
    return edges.filter((e) => bucketRel(e.tipo) === relFilter);
  }, [edges, relFilter]);

  const visibleNodeIds = useMemo(() => {
    const ids = new Set<string>();
    if (centro) ids.add(centro);
    visibleEdges.forEach((e) => {
      ids.add(e.from);
      ids.add(e.to);
    });
    if (!visibleEdges.length) nodes.forEach((n) => ids.add(n.id));
    return ids;
  }, [visibleEdges, nodes, centro]);

  const visibleNodes = useMemo(
    () => nodes.filter((n) => visibleNodeIds.has(n.id)),
    [nodes, visibleNodeIds]
  );

  // Chaves estáveis — evita recriar o grafo a cada render do pai.
  const graphKey = useMemo(() => {
    const n = visibleNodes
      .map((x) => `${x.id}:${x.image || ""}`)
      .sort()
      .join("|");
    const e = visibleEdges
      .map((x) => x.id)
      .sort()
      .join("|");
    return `${centro || ""}::${expand ? 1 : 0}::${n}::${e}`;
  }, [visibleNodes, visibleEdges, centro, expand]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let alive = true;
    el.style.pointerEvents = "auto";

    const elements = [
      ...visibleNodes.map((n) => ({
        data: {
          id: n.id,
          label: shortLabel(n.nome, n.tipo === "pessoa" ? 18 : 24),
          full: n.nome,
          tipo: n.tipo,
          color: colorForEntity(n.tipo),
          isCentro: n.id === centro ? 1 : 0,
          hasImage: n.image ? 1 : 0,
          image: n.image || "",
        },
      })),
      ...visibleEdges.map((e) => ({
        data: {
          id: e.id,
          source: e.from,
          target: e.to,
          label: (e.tipo || "").replace(/_/g, " "),
          color: colorForRelation(e.tipo),
          grau: e.grau_confirmacao || "",
        },
      })),
    ];

    const heavy = visibleNodes.length > 40;
    const cy = cytoscape({
      container: el,
      elements,
      minZoom: 0.2,
      maxZoom: 4,
      // 0.35 era lento; 1.55 ficou agressivo demais
      wheelSensitivity: 0.85,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#1a2625",
            "background-opacity": 1,
            "border-width": 2.5,
            "border-color": "data(color)",
            label: "data(label)",
            color: "#FAF8F2",
            "font-size": 13,
            "font-weight": 600,
            "font-family": "IBM Plex Sans, sans-serif",
            "text-valign": "bottom",
            "text-margin-y": 10,
            "text-outline-width": 3,
            "text-outline-color": "#0c1212",
            "text-max-width": 90,
            "text-wrap": "wrap",
            width: 42,
            height: 42,
            "overlay-padding": 8,
            "overlay-opacity": 0,
            "z-index-compare": "manual",
            "z-index": 10,
          },
        },
        {
          selector: "node[hasImage = 1]",
          style: {
            "background-image": "data(image)",
            "background-fit": "cover",
            "background-clip": "node",
            "background-image-opacity": 1,
            "background-color": "#24302F",
            width: 48,
            height: 48,
            shape: "ellipse",
          },
        },
        {
          selector: "node[tipo = 'grupo'], node[tipo = 'supernode']",
          style: {
            shape: "round-rectangle",
            width: 100,
            height: 36,
            "font-size": 11,
            "background-color": "#24302F",
          },
        },
        {
          selector: "node[tipo = 'caso'], node[tipo = 'operacao']",
          style: {
            shape: "round-rectangle",
            width: 72,
            height: 40,
            "font-size": 12,
            "background-color": "#1e2c2a",
          },
        },
        {
          selector: "node[tipo = 'empresa'], node[tipo = 'instituicao'], node[tipo = 'partido']",
          style: {
            shape: "round-rectangle",
            width: 56,
            height: 34,
            "font-size": 11,
          },
        },
        {
          selector: "node[isCentro = 1]",
          style: {
            width: 58,
            height: 58,
            "border-width": 4,
            "border-color": "#3d9b84",
            "background-color": "#182120",
            "font-size": 14,
            "z-index": 20,
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 4,
            "border-color": "#FAF8F2",
            "background-color": "#24302F",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.6,
            "line-color": "data(color)",
            "target-arrow-color": "data(color)",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.85,
            opacity: 0.55,
            label: expand ? "data(label)" : "",
            "font-size": 10,
            color: "#C5CFCB",
            "text-rotation": "autorotate",
            "text-margin-y": -8,
            "text-outline-width": 2,
            "text-outline-color": "#0c1212",
            "z-index": 1,
          },
        },
        {
          selector: "edge:selected",
          style: {
            width: 3,
            opacity: 1,
          },
        },
      ],
      // animate:false evita rAF após unmount (notify null)
      layout: heavy
        ? ({
            name: "concentric",
            animate: false,
            padding: 56,
            minNodeSpacing: 28,
            concentric: (n: cytoscape.NodeSingular) =>
              n.data("isCentro") === 1 ? 100 : n.degree(),
            levelWidth: () => 2,
          } as cytoscape.LayoutOptions)
        : ({
            name: "cose",
            animate: false,
            padding: 64,
            nodeRepulsion: expand ? 900000 : 650000,
            idealEdgeLength: expand ? 140 : 110,
            nestingFactor: 1.2,
            gravity: 0.85,
            numIter: 500,
            randomize: true,
          } as cytoscape.LayoutOptions),
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
    });

    if (!alive) {
      destroyCy(cy, el);
      return;
    }

    if (centro && cy.$id(centro).length) {
      cy.$id(centro).select();
      setSelected(centro);
    }

    // Enquadra depois do layout síncrono
    try {
      cy.fit(undefined, 48);
      // leve aproximação para legibilidade
      const z = cy.zoom();
      if (z < 0.85) cy.zoom(Math.min(1.15, Math.max(0.85, z * 1.25)));
      cy.center();
    } catch {
      /* ignore */
    }

    const runIfAlive = (fn: () => void) => {
      if (!alive || cy.destroyed()) return;
      try {
        fn();
      } catch {
        /* hover após destroy */
      }
    };

    cy.on("tap", "node", (evt) => {
      runIfAlive(() => {
        const id = evt.target.id();
        const tipo = evt.target.data("tipo") as string;
        setSelected(id);
        cy.elements().unselect();
        evt.target.select();
        evt.target.connectedEdges().select();
        if (
          tipo === "supernode" ||
          tipo === "grupo" ||
          String(id).startsWith("sn::")
        ) {
          routerRef.current.push(hrefForEntity(id, tipo || "supernode"));
        }
      });
    });

    cy.on("tap", (evt) => {
      runIfAlive(() => {
        if (evt.target === cy) {
          setSelected(null);
          cy.elements().unselect();
        }
      });
    });

    cy.on("dbltap", "node", (evt) => {
      runIfAlive(() => {
        const id = evt.target.id();
        const tipo = evt.target.data("tipo") as string;
        const node = byId[id] || { id, nome: id, tipo };
        const custom = hrefForNodeRef.current?.(node);
        if (custom === null) return;
        routerRef.current.push(custom || hrefForEntity(id, tipo));
      });
    });

    cyRef.current = cy;

    return () => {
      alive = false;
      layoutRef.current?.stop?.();
      layoutRef.current = null;
      cyRef.current = null;
      destroyCy(cy, el);
    };
    // graphKey já encapsula nós/arestas/centro/expand
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphKey]);

  function safeCy(): Core | null {
    const cy = cyRef.current;
    if (!cy || cy.destroyed()) return null;
    return cy;
  }

  function zoomBy(factor: number) {
    const cy = safeCy();
    if (!cy) return;
    try {
      const z = cy.zoom() * factor;
      cy.zoom({
        level: Math.min(4, Math.max(0.2, z)),
        renderedPosition: {
          x: (wrapRef.current?.clientWidth || 400) / 2,
          y: (wrapRef.current?.clientHeight || 400) / 2,
        },
      });
    } catch {
      /* ignore */
    }
  }

  function relayout() {
    const cy = safeCy();
    if (!cy) return;
    setRunning(true);
    try {
      layoutRef.current?.stop?.();
      const layout = cy.layout({
        name: "cose",
        // animação curta + stop no cleanup evita notify null
        animate: true,
        animationDuration: 280,
        padding: 64,
        nodeRepulsion: expand ? 950000 : 700000,
        idealEdgeLength: expand ? 150 : 120,
        randomize: true,
        numIter: 450,
      } as cytoscape.LayoutOptions);
      layoutRef.current = layout;
      layout.one("layoutstop", () => {
        layoutRef.current = null;
        setRunning(false);
        try {
          if (!cy.destroyed()) cy.fit(undefined, 48);
        } catch {
          /* ignore */
        }
      });
      layout.run();
    } catch {
      setRunning(false);
    }
  }

  function fit() {
    const cy = safeCy();
    if (!cy) return;
    try {
      cy.fit(undefined, 48);
    } catch {
      /* ignore */
    }
  }

  const sel = selected ? byId[selected] : null;
  const selEdges = sel
    ? visibleEdges.filter((e) => e.from === sel.id || e.to === sel.id)
    : [];

  if (!nodes.length) {
    return <p className="muted">Sem nós neste filtro.</p>;
  }

  return (
    <div className="igraph">
      <div className="igraph-toolbar">
        <div className="chips">
          {REL_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`chip ${relFilter === f.id ? "active" : ""}`}
              onClick={() => setRelFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="igraph-actions">
          <label className="expand-toggle">
            <span>Modo expansão</span>
            <button
              type="button"
              className={`switch ${expand ? "on" : ""}`}
              aria-pressed={expand}
              onClick={() => setExpand((v) => !v)}
            />
          </label>
          <button
            type="button"
            className="btn-ghost"
            onClick={relayout}
            disabled={running}
          >
            {running ? "Calculando…" : "Relayout"}
          </button>
          <button type="button" className="btn-ghost" onClick={fit}>
            Enquadrar
          </button>
        </div>
      </div>

      <div className="igraph-canvas-wrap" ref={wrapRef}>
        <div className="igraph-zoom" aria-label="Zoom">
          <button type="button" title="Ampliar" onClick={() => zoomBy(1.2)}>
            +
          </button>
          <button type="button" title="Reduzir" onClick={() => zoomBy(1 / 1.2)}>
            −
          </button>
          <button type="button" title="Enquadrar" onClick={fit}>
            ⛶
          </button>
        </div>
        <div className="igraph-canvas igraph-cy" ref={ref} />
      </div>

      <div className="igraph-foot">
        <p className="faint">
          {visibleNodes.length} nós · {visibleEdges.length} arestas
        </p>
        {sel && (
          <div className="igraph-sel">
            <div className="igraph-sel-main">
              {sel.image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={sel.image}
                  alt=""
                  className="igraph-sel-photo"
                  width={40}
                  height={40}
                />
              ) : null}
              <div>
                <strong style={{ color: "var(--ink)" }}>{sel.nome}</strong>
                <span className="faint"> · {sel.tipo}</span>
                <p
                  className="muted"
                  style={{ fontSize: "0.8rem", margin: "0.25rem 0 0" }}
                >
                  {selEdges.length} relação(ões) visíveis neste filtro
                </p>
              </div>
            </div>
            <div className="chips">
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  const custom = hrefForNode?.(sel);
                  if (custom === null) return;
                  routerRef.current.push(
                    custom || hrefForEntity(sel.id, sel.tipo)
                  );
                }}
              >
                Abrir perfil
              </button>
              <button
                type="button"
                className="btn-outline accent"
                onClick={() =>
                  routerRef.current.push(
                    `/grafo?centro=${encodeURIComponent(
                      sel.id
                    )}&profundidade=1&max_nodes=50`
                  )
                }
              >
                Abrir ego (teto 50)
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
