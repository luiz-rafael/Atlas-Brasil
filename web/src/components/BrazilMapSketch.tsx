/** Mapa esquemático do Brasil com hotspots coloridos (dashboard / território). */
type Props = {
  heat?: boolean;
};

export default function BrazilMapSketch({ heat = false }: Props) {
  const hotspots = [
    { x: 210, y: 95, c: "var(--cat-politica)", r: 7 },
    { x: 250, y: 140, c: "var(--cat-empresas)", r: 9 },
    { x: 180, y: 180, c: "var(--cat-crime)", r: 11 },
    { x: 280, y: 200, c: "var(--cat-instituicoes)", r: 8 },
    { x: 220, y: 260, c: "var(--cat-territorio)", r: 10 },
    { x: 160, y: 300, c: "var(--cat-politica)", r: 6 },
    { x: 240, y: 320, c: "var(--cat-empresas)", r: 8 },
    { x: 200, y: 220, c: "var(--cat-historia)", r: 5 },
  ];

  return (
    <svg viewBox="0 0 400 420" width="100%" height="100%" aria-label="Mapa do Brasil">
      <defs>
        <linearGradient id="land" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#143044" />
          <stop offset="100%" stopColor="#0c1822" />
        </linearGradient>
        {heat && (
          <radialGradient id="heat" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity="0" />
          </radialGradient>
        )}
      </defs>
      {/* silhueta aproximada */}
      <path
        d="M210 36 L250 48 L290 70 L310 110 L318 150 L305 190 L290 230 L270 270 L255 310 L245 350 L230 380 L200 390 L175 370 L160 330 L145 290 L130 250 L120 210 L125 170 L145 130 L170 90 L190 55 Z"
        fill="url(#land)"
        stroke="#2a4258"
        strokeWidth="2"
      />
      {heat &&
        hotspots.map((h, i) => (
          <circle key={`h${i}`} cx={h.x} cy={h.y} r={h.r * 3.2} fill="url(#heat)" />
        ))}
      {hotspots.map((h, i) => (
        <circle
          key={i}
          cx={h.x}
          cy={h.y}
          r={h.r}
          fill={h.c}
          opacity={0.9}
          stroke="#0a121a"
          strokeWidth="1.5"
        >
          <animate
            attributeName="r"
            values={`${h.r};${h.r + 1.5};${h.r}`}
            dur={`${2.4 + (i % 3) * 0.4}s`}
            repeatCount="indefinite"
          />
        </circle>
      ))}
      {/* divisões leves */}
      <path
        d="M180 120 L260 160 M160 200 L280 210 M170 280 L250 300"
        stroke="#2a4258"
        strokeWidth="1"
        strokeDasharray="4 6"
        fill="none"
        opacity="0.6"
      />
    </svg>
  );
}
