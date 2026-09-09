/** Mapa do Brasil estilizado em constelação (landing) — ATLAS INK. */
export default function BrazilConstellation() {
  // pontos aproximados (viewBox 0 0 400 420)
  const nodes = [
    [210, 40],
    [180, 80],
    [240, 90],
    [160, 130],
    [220, 140],
    [280, 120],
    [140, 180],
    [200, 190],
    [260, 175],
    [300, 160],
    [120, 230],
    [180, 240],
    [240, 230],
    [290, 210],
    [150, 290],
    [210, 300],
    [260, 280],
    [190, 350],
    [230, 360],
    [250, 320],
  ];
  const edges: [number, number][] = [
    [0, 1],
    [0, 2],
    [1, 3],
    [1, 4],
    [2, 4],
    [2, 5],
    [3, 6],
    [4, 7],
    [4, 8],
    [5, 9],
    [6, 10],
    [7, 11],
    [8, 12],
    [9, 13],
    [10, 14],
    [11, 15],
    [12, 16],
    [14, 17],
    [15, 18],
    [16, 19],
    [15, 19],
    [7, 12],
    [11, 14],
  ];

  return (
    <svg
      viewBox="0 0 400 420"
      width="100%"
      height="100%"
      style={{ position: "absolute", inset: 0, opacity: 0.9 }}
      aria-hidden
    >
      <defs>
        <radialGradient id="glow" cx="50%" cy="45%" r="55%">
          <stop offset="0%" stopColor="#276052" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#101717" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="400" height="420" fill="url(#glow)" />
      {edges.map(([a, b], i) => (
        <line
          key={i}
          x1={nodes[a][0]}
          y1={nodes[a][1]}
          x2={nodes[b][0]}
          y2={nodes[b][1]}
          stroke="#315D78"
          strokeOpacity="0.32"
          strokeWidth="1"
        />
      ))}
      {nodes.map(([x, y], i) => (
        <circle
          key={i}
          className="constellation-node"
          cx={x}
          cy={y}
          r={i % 4 === 0 ? 4.5 : 2.8}
          fill={i % 3 === 0 ? "#276052" : i % 3 === 1 ? "#315D78" : "#A47B32"}
          style={{ animationDelay: `${(i % 7) * 0.25}s` }}
        />
      ))}
    </svg>
  );
}
