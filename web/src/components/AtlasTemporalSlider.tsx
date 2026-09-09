"use client";

import Link from "next/link";

/**
 * AtlasTemporalSlider — seletor de ano via Form GET.
 * Fase D.
 */
export default function AtlasTemporalSlider({
  years,
  year,
  basePath,
  preserve,
}: {
  years: number[];
  year: number;
  basePath: string;
  preserve?: Record<string, string | undefined>;
}) {
  const qs = (y: number) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(preserve || {})) {
      if (v != null && v !== "") p.set(k, v);
    }
    p.set("ano", String(y));
    return `${basePath}?${p.toString()}`;
  };

  const min = years[0] ?? 2000;
  const max = years[years.length - 1] ?? 2026;
  const step = Math.max(1, Math.floor(years.length / 12));
  const chips = years
    .filter((_, i) => i % step === 0)
    .concat(years.includes(year) ? [] : [year])
    .filter((y, i, a) => a.indexOf(y) === i)
    .sort((a, b) => a - b);

  return (
    <div className="stack" style={{ gap: "0.6rem" }}>
      <form method="get" action={basePath} className="temporal-row">
        {Object.entries(preserve || {}).map(([k, v]) =>
          v != null && v !== "" ? (
            <input key={k} type="hidden" name={k} value={v} />
          ) : null
        )}
        <label className="faint" htmlFor="atlas-ano">
          Ano de referência
        </label>
        <input
          id="atlas-ano"
          type="range"
          name="ano"
          min={min}
          max={max}
          defaultValue={year}
          list="atlas-anos"
        />
        <datalist id="atlas-anos">
          {years.map((y) => (
            <option key={y} value={y} />
          ))}
        </datalist>
        <span className="item-title" style={{ minWidth: 48 }}>
          {year}
        </span>
        <button className="btn" type="submit">
          Aplicar
        </button>
      </form>
      <div className="chips">
        {chips.map((y) => (
          <Link
            key={y}
            className={`chip${y === year ? " active" : ""}`}
            href={qs(y)}
          >
            {y}
          </Link>
        ))}
      </div>
    </div>
  );
}
