"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { BR_STATE_PATHS } from "@/lib/br-states-paths";
import { formatIndicatorValue } from "@/lib/format";

type Props = {
  year: number;
  values: Record<string, number>;
  unitLabel?: string;
  indicatorId?: string;
  detailBase?: string;
};

function heat(t: number) {
  if (t <= 0) return "#24302F";
  if (t < 0.33) return `rgba(49,93,120,${0.28 + t * 0.5})`;
  if (t < 0.66) return `rgba(39,96,82,${0.35 + t * 0.4})`;
  return `rgba(164,123,50,${0.4 + t * 0.4})`;
}

export default function IndicatorChoropleth({
  year,
  values,
  unitLabel = "pessoas",
  indicatorId,
  detailBase = "/indicadores/uf",
}: Props) {
  const [sel, setSel] = useState<string | null>(null);
  const max = useMemo(
    () => Math.max(1, ...Object.values(values).map(Number)),
    [values]
  );
  const selectedVal = sel ? values[sel] : null;
  const fmt = (v: number) =>
    indicatorId
      ? formatIndicatorValue(indicatorId, v)
      : v.toLocaleString("pt-BR");

  return (
    <div className="stack">
      <div className="tmap-canvas" style={{ minHeight: 360 }}>
        <svg viewBox="0 0 1000 920" role="img" aria-label={`Mapa população ${year}`}>
          {BR_STATE_PATHS.map((s) => {
            const v = values[s.uf] || 0;
            const t = v / max;
            return (
              <path
                key={s.uf}
                d={s.d}
                fill={heat(t)}
                stroke={sel === s.uf ? "#FAF8F2" : "#101717"}
                strokeWidth={sel === s.uf ? 2 : 0.7}
                style={{ cursor: "pointer" }}
                onClick={() => setSel(s.uf === sel ? null : s.uf)}
              >
                <title>
                  {s.nome}: {v ? fmt(v) : "sem dado"} ({unitLabel})
                </title>
              </path>
            );
          })}
        </svg>
      </div>
      <div className="panel stack">
        <p className="muted">
          Ano <strong>{year}</strong> · cor proporcional ao valor (máx.{" "}
          {max.toLocaleString("pt-BR")} {unitLabel}). Clique um estado.
        </p>
        {sel ? (
          <div>
            <p className="item-title">
              {BR_STATE_PATHS.find((x) => x.uf === sel)?.nome || sel}
            </p>
            <p className="item-meta">
              {selectedVal != null
                ? `${fmt(selectedVal)} · ${unitLabel}`
                : "Sem observação neste ano"}
            </p>
            <div className="chips" style={{ marginTop: "0.5rem" }}>
              <Link className="chip" href={`${detailBase}/${sel}`}>
                Série histórica
              </Link>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
