/**
 * Grafo SVG (SSR-safe) — não depende de chunks client/Cytoscape.
 */

export type SvgNode = {
  id: string;
  nome: string;
  tipo: string;
};

export type SvgEdge = {
  id: string;
  from: string;
  to: string;
  tipo: string;
  grau_confirmacao?: string;
};

const TYPE_COLOR: Record<string, string> = {
  pessoa: "#7d9b6a",
  empresa: "#c4a35a",
  partido: "#6a8f9b",
  instituicao: "#9b7d6a",
  caso: "#8b6a9b",
  faccao: "#a35a5a",
  operacao: "#5a7aa3",
};

function layoutRadial(
  centro: string | undefined,
  nodeIds: string[]
): Record<string, { x: number; y: number }> {
  const pos: Record<string, { x: number; y: number }> = {};
  const cx = 320;
  const cy = 220;
  const others = nodeIds.filter((id) => id !== centro);
  if (centro && nodeIds.includes(centro)) {
    pos[centro] = { x: cx, y: cy };
  }
  const n = Math.max(others.length, 1);
  const r = Math.min(160, 40 + n * 18);
  others.forEach((id, i) => {
    const a = (2 * Math.PI * i) / n - Math.PI / 2;
    pos[id] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  });
  // se não há centro, grid
  if (!centro || !nodeIds.includes(centro)) {
    const cols = Math.min(4, Math.max(2, Math.ceil(Math.sqrt(nodeIds.length))));
    nodeIds.forEach((id, i) => {
      pos[id] = {
        x: 60 + (i % cols) * 150,
        y: 50 + Math.floor(i / cols) * 100,
      };
    });
  }
  return pos;
}

function shortLabel(nome: string, max = 18) {
  return nome.length > max ? nome.slice(0, max - 1) + "…" : nome;
}

function hrefFor(id: string, tipo: string) {
  if (tipo === "pessoa") return `/pessoas/${id}`;
  if (tipo === "empresa") return `/empresas/${id}`;
  if (tipo === "partido") return `/partidos/${id}`;
  if (tipo === "instituicao") return `/instituicoes/${id}`;
  if (tipo === "caso") return `/casos/${id}`;
  return `/grafo?centro=${id}&profundidade=1`;
}

export default function GraphSvg({
  nodes,
  edges,
  centro,
}: {
  nodes: SvgNode[];
  edges: SvgEdge[];
  centro?: string;
}) {
  if (!nodes.length) {
    return <p className="muted">Sem nós neste filtro.</p>;
  }

  const ids = nodes.map((n) => n.id);
  const pos = layoutRadial(centro, ids);
  const width = 640;
  const height = 440;

  return (
    <div className="graph-svg-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={480}
        role="img"
        aria-label="Grafo de relações"
        style={{
          background: "#101717",
          border: "1px solid #2a2a28",
          borderRadius: 4,
          display: "block",
        }}
      >
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#5a5a52" />
          </marker>
        </defs>

        {edges.map((e) => {
          const a = pos[e.from];
          const b = pos[e.to];
          if (!a || !b) return null;
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          return (
            <g key={e.id}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="#3a3a36"
                strokeWidth={1.5}
                markerEnd="url(#arrow)"
              />
              <text
                x={mx}
                y={my - 4}
                fill="#8a887f"
                fontSize={8}
                textAnchor="middle"
              >
                {e.tipo.replace(/_/g, " ")}
              </text>
            </g>
          );
        })}

        {nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const isCentro = n.id === centro;
          const color = TYPE_COLOR[n.tipo] || "#7d9b6a";
          const r = isCentro ? 18 : 12;
          return (
            <a key={n.id} href={hrefFor(n.id, n.tipo)}>
              <circle
                cx={p.x}
                cy={p.y}
                r={r}
                fill={color}
                stroke={isCentro ? "#c4a35a" : "#2a2a28"}
                strokeWidth={isCentro ? 3 : 2}
              />
              <text
                x={p.x}
                y={p.y + r + 12}
                fill="#e8e6e1"
                fontSize={10}
                textAnchor="middle"
              >
                {shortLabel(n.nome)}
              </text>
            </a>
          );
        })}
      </svg>
      <p className="faint" style={{ marginTop: "0.5rem" }}>
        Clique em um nó para abrir. Centro destacado em dourado.
      </p>
    </div>
  );
}
