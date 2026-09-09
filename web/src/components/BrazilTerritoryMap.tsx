"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { BR_STATE_PATHS } from "@/lib/br-states-paths";
import { buildTerritoryHotspots, type TerritoryHotspot } from "@/lib/geo-br";
import { colorForEntity } from "@/lib/viz-colors";

export type LayerKey =
  | "pessoas"
  | "empresas"
  | "instituicoes"
  | "crime"
  | "relacoes"
  | "rede";

const LAYER_META: { id: LayerKey; label: string; defaultOn: boolean }[] = [
  { id: "pessoas", label: "Pessoas / política", defaultOn: true },
  { id: "empresas", label: "Empresas", defaultOn: true },
  { id: "instituicoes", label: "Instituições", defaultOn: true },
  { id: "crime", label: "Organizações criminosas", defaultOn: true },
  { id: "relacoes", label: "Relações (peso)", defaultOn: true },
  { id: "rede", label: "Rede entre UFs", defaultOn: true },
];

type Props = {
  kb: {
    entidades: Array<{
      id: string;
      tipo: string;
      uf?: string | null;
      isolada?: boolean;
      tags?: string[];
      nome?: string;
      cargo_atual?: string | null;
    }>;
    relacoes: Array<{ origem: string; destino: string; tipo?: string }>;
  };
  showLegend?: boolean;
  compact?: boolean;
  themeFilter?: string | null;
  onSelectUf?: (uf: string | null) => void;
};

function weightWithLayers(h: TerritoryHotspot, on: Record<LayerKey, boolean>) {
  let w = 0;
  if (on.pessoas) w += h.pessoas * 3;
  if (on.empresas) w += h.empresas * 2;
  if (on.instituicoes) w += h.instituicoes * 2;
  if (on.crime) w += h.crime * 5;
  if (on.relacoes) w += h.relacoes;
  return w;
}

function heatFill(t: number, active: boolean) {
  if (t <= 0) return active ? "#24302F" : "#182120";
  if (t < 0.35) return `rgba(49,93,120,${0.28 + t * 0.5})`;
  if (t < 0.65) return `rgba(39,96,82,${0.35 + t * 0.35})`;
  return `rgba(164,123,50,${0.42 + t * 0.4})`;
}

export default function BrazilTerritoryMap({
  kb,
  showLegend = true,
  compact = false,
  themeFilter = null,
  onSelectUf,
}: Props) {
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(() =>
    Object.fromEntries(LAYER_META.map((l) => [l.id, l.defaultOn])) as Record<
      LayerKey,
      boolean
    >
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{
    sx: number;
    sy: number;
    ox: number;
    oy: number;
  } | null>(null);

  const hotspots = useMemo(() => buildTerritoryHotspots(kb), [kb]);
  const byUf = useMemo(() => {
    const m = new Map<string, TerritoryHotspot>();
    hotspots.forEach((h) => m.set(h.uf, h));
    return m;
  }, [hotspots]);

  const filtered = useMemo(() => {
    return hotspots
      .map((h) => {
        let w = weightWithLayers(h, layers);
        if (themeFilter === "empresas") w = h.empresas * 4;
        if (themeFilter === "politica") w = h.pessoas * 4;
        if (themeFilter === "crime") w = h.crime * 8;
        if (themeFilter === "instituicoes") w = h.instituicoes * 5;
        if (themeFilter === "casos") w = h.instituicoes * 2 + h.relacoes;
        if (themeFilter === "docs") w = h.relacoes + h.pessoas;
        return { ...h, weight: w };
      })
      .filter((h) => h.weight > 0);
  }, [hotspots, layers, themeFilter]);

  const weightMap = useMemo(() => {
    const m = new Map<string, number>();
    filtered.forEach((h) => m.set(h.uf, h.weight));
    return m;
  }, [filtered]);

  const maxW = Math.max(1, ...filtered.map((h) => h.weight));

  const links = useMemo(() => {
    if (!layers.rede) return [] as { x1: number; y1: number; x2: number; y2: number; key: string }[];
    const idTo = new Map<string, TerritoryHotspot>();
    for (const h of filtered) {
      for (const id of h.entityIds) idTo.set(id, h);
    }
    const seen = new Set<string>();
    const out: { x1: number; y1: number; x2: number; y2: number; key: string }[] = [];
    for (const r of kb.relacoes) {
      const a = idTo.get(r.origem);
      const b = idTo.get(r.destino);
      if (!a || !b || a.uf === b.uf) continue;
      const key = [a.uf, b.uf].sort().join("-");
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y, key });
    }
    return out.slice(0, 48);
  }, [kb.relacoes, filtered, layers.rede]);

  function pick(uf: string) {
    const next = selected === uf ? null : uf;
    setSelected(next);
    onSelectUf?.(next);
  }

  const detail = selected
    ? filtered.find((h) => h.uf === selected) || byUf.get(selected) || null
    : null;

  return (
    <div className={`tmap ${compact ? "compact" : ""}`}>
      <div className="tmap-stage">
        <div className="tmap-zoom">
          <button type="button" onClick={() => setZoom((z) => Math.min(2.4, z * 1.15))}>
            +
          </button>
          <button type="button" onClick={() => setZoom((z) => Math.max(0.65, z * 0.88))}>
            −
          </button>
          <button
            type="button"
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
            title="Reset"
          >
            ↺
          </button>
        </div>
        <svg
          viewBox="0 0 1000 920"
          className="tmap-svg"
          aria-label="Mapa territorial do Brasil"
          onPointerDown={(e) => {
            if ((e.target as Element).closest("[data-uf]")) return;
            (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
            drag.current = { sx: e.clientX, sy: e.clientY, ox: pan.x, oy: pan.y };
          }}
          onPointerMove={(e) => {
            if (!drag.current) return;
            setPan({
              x: drag.current.ox + (e.clientX - drag.current.sx),
              y: drag.current.oy + (e.clientY - drag.current.sy),
            });
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerLeave={() => {
            drag.current = null;
          }}
        >
          <rect width="1000" height="920" fill="transparent" />
          <g
            transform={`translate(${500 + pan.x} ${460 + pan.y}) scale(${zoom}) translate(-500 -460)`}
          >
            {BR_STATE_PATHS.map((st) => {
              const w = weightMap.get(st.uf) || 0;
              const t = w / maxW;
              const active = selected === st.uf;
              return (
                <path
                  key={st.uf}
                  data-uf={st.uf}
                  d={st.d}
                  fill={heatFill(t, active)}
                  stroke={active ? "#f8fafc" : "#2a4258"}
                  strokeWidth={active ? 2.2 : 1.1}
                  style={{ cursor: "pointer", transition: "fill 0.2s ease" }}
                  aria-label={`${st.nome} (${st.uf})${w > 0 ? ` · peso ${w}` : " · sem dados no filtro"}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    pick(st.uf);
                  }}
                />
              );
            })}

            {links.map((l) => (
              <line
                key={l.key}
                x1={l.x1}
                y1={l.y1}
                x2={l.x2}
                y2={l.y2}
                stroke="#315D78"
                strokeOpacity="0.4"
                strokeWidth="1.6"
                style={{ pointerEvents: "none" }}
              />
            ))}

            {filtered.map((h) => {
              const t = h.weight / maxW;
              const active = selected === h.uf;
              return (
                <g
                  key={`dot-${h.uf}`}
                  data-uf={h.uf}
                  style={{ cursor: "pointer" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    pick(h.uf);
                  }}
                >
                  <circle
                    cx={h.x}
                    cy={h.y}
                    r={8 + t * 16}
                    fill={heatFill(Math.min(1, t + 0.2), active)}
                    stroke={active ? "#fff" : "transparent"}
                    strokeWidth={active ? 2 : 0}
                    opacity={0.9}
                  />
                  <circle
                    cx={h.x}
                    cy={h.y}
                    r={4 + t * 4}
                    fill={
                      h.crime > 0
                        ? colorForEntity("faccao")
                        : h.empresas > h.pessoas
                          ? colorForEntity("empresa")
                          : colorForEntity("pessoa")
                    }
                  />
                  <text
                    x={h.x}
                    y={h.y + 22}
                    textAnchor="middle"
                    fill="#AEB8B4"
                    fontSize="10"
                    style={{ pointerEvents: "none" }}
                  >
                    {h.uf}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>

        {legendOpen && showLegend && (
          <div className="map-legend">
            <strong style={{ color: "var(--ink)" }}>Legenda</strong>
            <div className="legend-item">
              <i style={{ background: "#D5C7A4" }} /> Política / pessoas
            </div>
            <div className="legend-item">
              <i style={{ background: "#4E7C72" }} /> Empresas
            </div>
            <div className="legend-item">
              <i style={{ background: "#55738B" }} /> Instituições
            </div>
            <div className="legend-item">
              <i style={{ background: "#76667F" }} /> Crime
            </div>
            <div className="legend-item">
              <i style={{ background: "linear-gradient(90deg,#315D78,#276052,#A47B32)" }} />{" "}
              Intensidade UF
            </div>
            <button
              type="button"
              className="btn-ghost"
              style={{ marginTop: 8, fontSize: "0.72rem" }}
              onClick={() => setLegendOpen(false)}
            >
              Ocultar legenda
            </button>
          </div>
        )}
        {!legendOpen && showLegend && (
          <button
            type="button"
            className="btn-ghost tmap-show-legend"
            onClick={() => setLegendOpen(true)}
          >
            Legenda
          </button>
        )}
      </div>

      {!compact && (
        <aside className="panel tmap-layers">
          <h2>Camadas</h2>
          {LAYER_META.map((l) => (
            <button
              key={l.id}
              type="button"
              className="layer-toggle"
              onClick={() =>
                setLayers((prev) => ({ ...prev, [l.id]: !prev[l.id] }))
              }
              style={{
                width: "100%",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span>{l.label}</span>
              <span className={`switch ${layers[l.id] ? "on" : ""}`} />
            </button>
          ))}
          <p className="faint" style={{ marginTop: "1rem" }}>
            Clique um estado · arraste o mapa · zoom ±
          </p>
          <div className="heat-bar" />
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: "0.72rem",
              color: "var(--ink-faint)",
            }}
          >
            <span>Baixa</span>
            <span>Alta</span>
          </div>

          {detail && (
            <div style={{ marginTop: "1.25rem" }}>
              <h2>
                {detail.nome} ({detail.uf})
              </h2>
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                Pessoas {detail.pessoas} · Empresas {detail.empresas} · Instit.{" "}
                {detail.instituicoes} · Crime {detail.crime} · Relações{" "}
                {detail.relacoes}
              </p>
              <div className="chips" style={{ marginTop: 8 }}>
                {detail.entityIds.slice(0, 8).map((id) => {
                  const e = kb.entidades.find((x) => x.id === id);
                  if (!e) return null;
                  const href =
                    e.tipo === "pessoa"
                      ? `/pessoas/${id}`
                      : e.tipo === "empresa"
                        ? `/empresas/${id}`
                        : e.tipo === "instituicao"
                          ? `/instituicoes/${id}`
                          : `/grafo?centro=${id}`;
                  return (
                    <Link key={id} className="chip" href={href}>
                      {e.nome}
                    </Link>
                  );
                })}
              </div>
              <div className="chips" style={{ marginTop: 10 }}>
                <Link
                  className="btn-outline accent"
                  href={`/explorar?q=${encodeURIComponent(detail.uf)}`}
                >
                  Explorar UF
                </Link>
                {detail.entityIds[0] && (
                  <Link
                    className="btn-primary"
                    href={`/grafo?centro=${detail.entityIds[0]}&profundidade=2`}
                  >
                    Ver no grafo
                  </Link>
                )}
              </div>
            </div>
          )}
        </aside>
      )}

      {compact && detail && (
        <div className="panel" style={{ marginTop: 10, padding: "0.75rem 1rem" }}>
          <strong style={{ color: "var(--ink)" }}>
            {detail.nome} ({detail.uf})
          </strong>
          <span className="faint">
            {" "}
            · {detail.pessoas}p · {detail.empresas}e · {detail.relacoes}r
          </span>
          <div className="chips" style={{ marginTop: 6 }}>
            {detail.entityIds.slice(0, 4).map((id) => {
              const e = kb.entidades.find((x) => x.id === id);
              if (!e) return null;
              return (
                <Link key={id} className="chip" href={`/grafo?centro=${id}`}>
                  {e.nome}
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
