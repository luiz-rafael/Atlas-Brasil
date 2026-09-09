"use client";

import { useEffect, useRef } from "react";
import cytoscape, { Core } from "cytoscape";
import Link from "next/link";

export type CyNode = {
  id: string;
  nome: string;
  tipo: string;
};

export type CyEdge = {
  id: string;
  from: string;
  to: string;
  tipo: string;
  grau_confirmacao?: string;
};

const TYPE_COLOR: Record<string, string> = {
  pessoa: "#D5C7A4",
  empresa: "#4E7C72",
  partido: "#807167",
  instituicao: "#55738B",
  caso: "#76667F",
  documento: "#8A918B",
  conceito: "#66736F",
  faccao: "#76667F",
  organizacao_criminosa: "#76667F",
  operacao: "#8B6C91",
};

function hrefFor(id: string, tipo: string) {
  if (tipo === "pessoa") return `/pessoas/${id}`;
  if (tipo === "empresa") return `/empresas/${id}`;
  if (tipo === "partido") return `/partidos/${id}`;
  if (tipo === "instituicao") return `/instituicoes/${id}`;
  if (tipo === "caso") return `/casos/${id}`;
  if (tipo === "documento") return `/fontes/${id}`;
  if (tipo === "faccao" || tipo === "organizacao_criminosa") return `/crime`;
  return `/grafo?centro=${id}`;
}

function destroyCy(cy: Core | null, container?: HTMLElement | null) {
  if (!cy) return;
  try {
    if (container) container.style.pointerEvents = "none";
    cy.removeAllListeners();
    cy.stop();
    if (!cy.destroyed()) cy.destroy();
  } catch {
    /* ignore */
  }
}

export default function GraphCanvas({
  nodes,
  edges,
  centro,
}: {
  nodes: CyNode[];
  edges: CyEdge[];
  centro?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let alive = true;
    el.style.pointerEvents = "auto";

    const cy = cytoscape({
      container: el,
      elements: [
        ...nodes.map((n) => ({
          data: {
            id: n.id,
            label: n.nome.length > 22 ? n.nome.slice(0, 20) + "…" : n.nome,
            full: n.nome,
            tipo: n.tipo,
            color: TYPE_COLOR[n.tipo] || "#7d9b6a",
          },
        })),
        ...edges.map((e) => ({
          data: {
            id: e.id,
            source: e.from,
            target: e.to,
            label: e.tipo.replace(/_/g, " "),
            grau: e.grau_confirmacao || "",
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#e8e6e1",
            "font-size": 10,
            "font-family": "Manrope, sans-serif",
            "text-valign": "bottom",
            "text-margin-y": 6,
            width: 28,
            height: 28,
            "border-width": 2,
            "border-color": "#2a2a28",
          },
        },
        {
          selector: `node[id = "${centro}"]`,
          style: {
            width: 40,
            height: 40,
            "border-color": "#c4a35a",
            "border-width": 3,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#3a3a36",
            "target-arrow-color": "#3a3a36",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 8,
            color: "#8a887f",
            "text-rotation": "autorotate",
            "text-margin-y": -8,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        padding: 30,
      },
      userZoomingEnabled: true,
      userPanningEnabled: true,
    });

    if (!alive) {
      destroyCy(cy, el);
      return;
    }

    cy.on("tap", "node", (evt) => {
      if (!alive || cy.destroyed()) return;
      try {
        const id = evt.target.id();
        const tipo = evt.target.data("tipo");
        window.location.href = hrefFor(id, tipo);
      } catch {
        /* ignore */
      }
    });

    cyRef.current = cy;
    return () => {
      alive = false;
      cyRef.current = null;
      destroyCy(cy, el);
    };
  }, [nodes, edges, centro]);

  return (
    <div>
      <div
        ref={ref}
        style={{
          width: "100%",
          height: 480,
          background: "#101717",
          border: "1px solid #2a2a28",
          borderRadius: 4,
        }}
      />
      <p className="faint" style={{ marginTop: "0.5rem" }}>
        Arraste para pan · scroll para zoom · clique no nó para abrir. Centro
        destacado.
        {centro ? (
          <>
            {" "}
            <Link href={`/grafo?centro=${centro}`}>Recarregar centro</Link>
          </>
        ) : null}
      </p>
    </div>
  );
}
