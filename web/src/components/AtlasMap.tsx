"use client";

import { useMemo } from "react";
import { BR_STATE_PATHS } from "@/lib/br-states-paths";
import { formatIndicatorValue } from "@/lib/format";
import { mapGovernorLabel } from "@/lib/indicator-taxonomy";

export type GovernorOnMap = {
  name: string;
  personId?: string | null;
  party?: string | null;
  start?: string | null;
  end?: string | null;
};

export type AtlasMapHover = {
  uf: string;
  nome: string;
  x: number;
  y: number;
};

type Props = {
  year: number;
  values: Record<string, number>;
  unitLabel?: string;
  indicatorId?: string;
  /** Hex do domínio — escala clara→escura = menor→maior valor. */
  domainHex?: string;
  higherIsBetter?: boolean;
  selectedUf?: string | null;
  governors?: Record<string, GovernorOnMap | null>;
  onSelect?: (uf: string) => void;
  onHover?: (hover: AtlasMapHover | null) => void;
};

type Leader = {
  dx: number;
  dy: number;
  gap?: number;
  anchor?: "start" | "middle" | "end";
};

const LEADERS: Record<string, Leader> = {
  AC: { dx: -70, dy: 10, gap: 18, anchor: "end" },
  AM: { dx: -55, dy: -55, gap: 28, anchor: "end" },
  RR: { dx: -20, dy: -55, gap: 16, anchor: "middle" },
  PA: { dx: 55, dy: -50, gap: 28, anchor: "start" },
  AP: { dx: 55, dy: -25, gap: 14, anchor: "start" },
  TO: { dx: 55, dy: -10, gap: 18, anchor: "start" },
  MA: { dx: 60, dy: -25, gap: 20, anchor: "start" },
  PI: { dx: 55, dy: 5, gap: 16, anchor: "start" },
  CE: { dx: 55, dy: -20, gap: 16, anchor: "start" },
  RN: { dx: 50, dy: -18, gap: 12, anchor: "start" },
  PB: { dx: 52, dy: 2, gap: 12, anchor: "start" },
  PE: { dx: 55, dy: 8, gap: 14, anchor: "start" },
  AL: { dx: 48, dy: 10, gap: 10, anchor: "start" },
  SE: { dx: 48, dy: 18, gap: 10, anchor: "start" },
  BA: { dx: 70, dy: 20, gap: 26, anchor: "start" },
  MT: { dx: -70, dy: 10, gap: 26, anchor: "end" },
  MS: { dx: -65, dy: 25, gap: 20, anchor: "end" },
  GO: { dx: -55, dy: -30, gap: 20, anchor: "end" },
  DF: { dx: 40, dy: -28, gap: 8, anchor: "start" },
  MG: { dx: 70, dy: 35, gap: 28, anchor: "start" },
  ES: { dx: 48, dy: 5, gap: 12, anchor: "start" },
  RJ: { dx: 55, dy: 25, gap: 12, anchor: "start" },
  SP: { dx: -70, dy: 40, gap: 24, anchor: "end" },
  PR: { dx: -65, dy: 30, gap: 20, anchor: "end" },
  SC: { dx: 55, dy: 30, gap: 16, anchor: "start" },
  RS: { dx: -55, dy: 45, gap: 24, anchor: "end" },
  RO: { dx: -60, dy: 25, gap: 16, anchor: "end" },
};

function parseHex(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((c) => c + c)
          .join("")
      : h;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

/** Escala quantitativa neutra: t=0 claro, t=1 escuro (cor do domínio). */
function quantitativeColor(hex: string, t: number): string {
  const [r, g, b] = parseHex(hex);
  const u = Math.max(0, Math.min(1, t));
  // mistura com paper claro → cor plena
  const lr = 247;
  const lg = 244;
  const lb = 234;
  const rr = Math.round(lr + (r - lr) * (0.25 + u * 0.75));
  const gg = Math.round(lg + (g - lg) * (0.25 + u * 0.75));
  const bb = Math.round(lb + (b - lb) * (0.25 + u * 0.75));
  return `rgb(${rr}, ${gg}, ${bb})`;
}

function quantile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const i = (sorted.length - 1) * p;
  const lo = Math.floor(i);
  const hi = Math.ceil(i);
  if (lo === hi) return sorted[lo];
  return sorted[lo] * (1 - (i - lo)) + sorted[hi] * (i - lo);
}

function leaderGeom(cx: number, cy: number, leader: Leader) {
  const len = Math.hypot(leader.dx, leader.dy) || 1;
  const ux = leader.dx / len;
  const uy = leader.dy / len;
  const gap = leader.gap ?? 16;
  return {
    x1: cx + ux * gap,
    y1: cy + uy * gap,
    x2: cx + leader.dx,
    y2: cy + leader.dy,
    anchor: leader.anchor || "middle",
  };
}

export default function AtlasMap({
  year,
  values,
  unitLabel = "valor",
  indicatorId,
  domainHex = "#285A78",
  higherIsBetter = true,
  selectedUf = null,
  governors = {},
  onSelect,
  onHover,
}: Props) {
  const nums = useMemo(
    () =>
      Object.values(values)
        .filter((v) => Number.isFinite(v))
        .sort((a, b) => a - b),
    [values]
  );

  const { lo, span } = useMemo(() => {
    if (!nums.length) return { lo: 0, span: 1 };
    const qLo = quantile(nums, 0.05);
    const qHi = quantile(nums, 0.95);
    const hi = qHi > qLo ? qHi : Math.max(...nums);
    return { lo: qLo, span: hi - qLo || 1 };
  }, [nums]);

  const absMin = nums.length ? nums[0] : 0;
  const absMax = nums.length ? nums[nums.length - 1] : 1;

  const fmt = (v: number) =>
    indicatorId
      ? formatIndicatorValue(indicatorId, v)
      : v.toLocaleString("pt-BR");

  const selectedGov = selectedUf ? governors[selectedUf] : null;
  const selectedNome = selectedUf
    ? BR_STATE_PATHS.find((s) => s.uf === selectedUf)?.nome
    : null;

  const legendLow = "Menor valor";
  const legendHigh = "Maior valor";
  const rankHint = higherIsBetter
    ? "No painel, ranking privilegia valores maiores."
    : "No painel, ranking privilegia valores menores (ex.: homicídios).";

  return (
    <div className="atlas-map-stage">
      <svg
        className="atlas-map-svg"
        viewBox="-40 -30 1080 980"
        role="img"
        aria-label={`Mapa do Brasil, ${year}. Escala: ${legendLow} a ${legendHigh}.`}
      >
        {BR_STATE_PATHS.map((s) => {
          const v = values[s.uf];
          const has = v != null && Number.isFinite(v);
          const active = selectedUf === s.uf;
          const gov = governors[s.uf];
          const t = has ? Math.max(0, Math.min(1, (v - lo) / span)) : 0;
          const fill = has ? quantitativeColor(domainHex, t) : "#e8e4d8";
          const tip = [
            s.nome,
            has ? fmt(v) : "sem dado",
            gov?.name
              ? `Governador(a) em ${year}: ${gov.name}${gov.party ? ` (${gov.party})` : ""}`
              : `Sem titular documentado em ${year}`,
          ].join("\n");

          return (
            <g
              key={s.uf}
              onMouseEnter={(e) => {
                const rect = (
                  e.currentTarget.ownerSVGElement as SVGSVGElement
                ).getBoundingClientRect();
                onHover?.({
                  uf: s.uf,
                  nome: s.nome,
                  x: e.clientX - rect.left,
                  y: e.clientY - rect.top,
                });
              }}
              onMouseMove={(e) => {
                const svg = e.currentTarget.ownerSVGElement;
                if (!svg) return;
                const rect = svg.getBoundingClientRect();
                onHover?.({
                  uf: s.uf,
                  nome: s.nome,
                  x: e.clientX - rect.left,
                  y: e.clientY - rect.top,
                });
              }}
              onMouseLeave={() => onHover?.(null)}
              onClick={() => onSelect?.(s.uf)}
              style={{ cursor: "pointer" }}
            >
              <title>{tip}</title>
              <path
                d={s.d}
                fill={fill}
                stroke={active ? domainHex : "#c9c5b8"}
                strokeWidth={active ? 2.2 : 0.8}
              />
              <text
                x={s.x}
                y={s.y + 4}
                textAnchor="middle"
                className={`atlas-map-uf${active ? " active" : ""}`}
                style={{ pointerEvents: "none" }}
              >
                {s.uf}
              </text>
            </g>
          );
        })}

        {BR_STATE_PATHS.map((s) => {
          const gov = governors[s.uf];
          if (!gov?.name) return null;
          const leader = LEADERS[s.uf] || {
            dx: 40,
            dy: -30,
            gap: 14,
            anchor: "start" as const,
          };
          const g = leaderGeom(s.x, s.y, leader);
          const active = selectedUf === s.uf;
          const label = mapGovernorLabel(gov.name);
          const pad = g.anchor === "end" ? -4 : g.anchor === "start" ? 4 : 0;

          return (
            <g
              key={`gov-${s.uf}`}
              className={`atlas-map-leader${active ? " active" : ""}`}
              style={{ pointerEvents: "none" }}
            >
              <line
                x1={g.x1}
                y1={g.y1}
                x2={g.x2}
                y2={g.y2}
                className="atlas-leader-line"
              />
              <circle cx={g.x1} cy={g.y1} r={1.8} className="atlas-leader-dot" />
              <text
                x={g.x2 + pad}
                y={g.y2 + 3}
                textAnchor={g.anchor}
                className={`atlas-map-gov${active ? " active" : ""}`}
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>

      {selectedUf && selectedGov?.name ? (
        <div className="atlas-map-nameplate">
          <span className="atlas-map-nameplate-uf">
            {selectedNome || selectedUf} · {year}
          </span>
          <strong>{selectedGov.name}</strong>
          {selectedGov.party ? (
            <span className="faint">{selectedGov.party}</span>
          ) : null}
        </div>
      ) : null}

      <div className="atlas-map-legend" aria-hidden="true">
        <div className="atlas-map-legend-row">
          <span className="atlas-leg-worse">{legendLow}</span>
          <i
            className="atlas-heat-bar"
            style={{
              background: `linear-gradient(90deg, ${quantitativeColor(domainHex, 0)}, ${quantitativeColor(domainHex, 1)})`,
            }}
          />
          <span className="atlas-leg-better">{legendHigh}</span>
        </div>
        <em>
          {nums.length
            ? `${fmt(absMin)} — ${fmt(absMax)}${unitLabel ? ` · ${unitLabel}` : ""}`
            : unitLabel}
          {" · "}
          {rankHint}
        </em>
      </div>
    </div>
  );
}
