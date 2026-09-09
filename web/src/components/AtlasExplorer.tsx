"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AtlasMap, {
  type AtlasMapHover,
  type GovernorOnMap,
} from "@/components/AtlasMap";
import { BR_STATE_PATHS, BR_STATE_BY_UF } from "@/lib/br-states-paths";
import {
  formatIndicatorValue,
  formatVariation,
  variationTone,
} from "@/lib/format";
import {
  ALL_ATLAS_INDICATORS,
  availableCategories,
  brasilAggregate,
  domainHex,
  rankAmong,
  yearInAdminRange,
  type AtlasLayer,
  type IndicatorDef,
} from "@/lib/indicator-taxonomy";
import PoliticosUfPanel from "@/components/PoliticosUfPanel";
import {
  POLITICO_CLASSE_LABEL,
  TIP_CLASSES,
  type PoliticosUfSummary,
} from "@/lib/politicos-by-uf";
export type AdminBand = {
  administration_id: string;
  state_code?: string;
  executive_person_name?: string | null;
  party_at_start?: string | null;
  start_date?: string | null;
  end_date?: string | null;
};

export type SeriesPoint = { year: number; value: number };

export type MunRow = {
  id: string;
  name: string;
  ibge?: string;
  value: number;
};

type Props = {
  layer: AtlasLayer;
  categoryId: string;
  indicator: IndicatorDef;
  categoryNote?: string;
  year: number;
  years: number[];
  nivel: "STATE" | "MUNICIPALITY";
  ufFilter: string;
  selectedUf: string | null;
  values: Record<string, number>;
  prevValues: Record<string, number>;
  prevYear: number | null;
  governors: Record<string, GovernorOnMap | null>;
  administrations: AdminBand[];
  series: SeriesPoint[];
  methodologyUrl?: string | null;
  datasetId?: string | null;
  description?: string | null;
  munRows: MunRow[];
  politicosByUf?: Record<string, PoliticosUfSummary>;
};

function href(opts: {
  layer: string;
  cat: string;
  ind: string;
  ano: number;
  nivel: string;
  uf?: string | null;
  sel?: string | null;
}) {
  const p = new URLSearchParams();
  p.set("camada", opts.layer);
  p.set("cat", opts.cat);
  p.set("ind", opts.ind);
  p.set("ano", String(opts.ano));
  p.set("nivel", opts.nivel);
  if (opts.nivel === "MUNICIPALITY" && opts.uf) p.set("uf", opts.uf);
  if (opts.sel) p.set("sel", opts.sel);
  return `/indicadores?${p.toString()}`;
}

function yearHref(base: Omit<Parameters<typeof href>[0], "ano">, ano: number) {
  return href({ ...base, ano });
}

function apiBase() {
  return (
    process.env.NEXT_PUBLIC_ATLAS_API_URL ||
    process.env.NEXT_PUBLIC_ATLAS_API ||
    "http://localhost:8001"
  ).replace(/\/$/, "");
}

export default function AtlasExplorer({
  layer,
  categoryId,
  indicator,
  categoryNote,
  year,
  years,
  nivel,
  ufFilter,
  selectedUf: selectedUfProp,
  values,
  prevValues,
  prevYear,
  governors,
  administrations,
  series: seriesProp,
  methodologyUrl,
  datasetId,
  description,
  munRows,
  politicosByUf = {},
}: Props) {
  const router = useRouter();
  const [sel, setSel] = useState<string | null>(selectedUfProp);
  const [hover, setHover] = useState<AtlasMapHover | null>(null);
  const [liveSeries, setLiveSeries] = useState<SeriesPoint[]>(seriesProp);
  const [playing, setPlaying] = useState(false);
  const playRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setSel(selectedUfProp);
  }, [selectedUfProp]);

  useEffect(() => {
    setLiveSeries(seriesProp);
  }, [seriesProp]);

  useEffect(() => {
    if (!sel) return;
    let cancelled = false;
    const qs = new URLSearchParams({
      territory_id: `uf_${sel}`,
      indicator_id: indicator.id,
    });
    fetch(`${apiBase()}/v1/indicadores/series?${qs}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data?.observations) return;
        const pts: SeriesPoint[] = data.observations
          .map((o: { reference_year: number; value: number }) => ({
            year: o.reference_year,
            value: o.value,
          }))
          .sort((a: SeriesPoint, b: SeriesPoint) => a.year - b.year);
        if (pts.length) setLiveSeries(pts);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [sel, indicator.id]);

  const qsBase = {
    layer,
    cat: categoryId,
    ind: indicator.id,
    nivel,
    uf: ufFilter,
    sel,
  };

  useEffect(() => {
    if (!playing) {
      if (playRef.current) clearInterval(playRef.current);
      playRef.current = null;
      return;
    }
    playRef.current = setInterval(() => {
      const idx = years.indexOf(year);
      const next = years[Math.min(years.length - 1, idx + 1)] ?? year;
      if (next === year || idx < 0) {
        setPlaying(false);
        return;
      }
      router.push(yearHref(qsBase, next));
    }, 1400);
    return () => {
      if (playRef.current) clearInterval(playRef.current);
    };
    // qsBase is rebuilt each render; year/years/router are the triggers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, year, years, layer, categoryId, indicator.id, nivel, ufFilter, sel]);

  const brasil = brasilAggregate(values, indicator.aggregation);
  const availableCats = availableCategories();
  const currentCat =
    availableCats.find((c) => c.id === categoryId) || availableCats[0];
  const domain = domainHex(categoryId);

  const panelUf = sel || hover?.uf || null;
  const panelNome = panelUf
    ? BR_STATE_BY_UF[panelUf]?.nome || panelUf
    : null;
  const panelVal = panelUf != null ? values[panelUf] : undefined;
  const panelPrev = panelUf != null ? prevValues[panelUf] : undefined;
  const panelVar = formatVariation(panelVal, panelPrev);
  const panelRank =
    panelUf != null
      ? rankAmong(values, panelUf, indicator.higherIsBetter)
      : null;
  const panelGov = panelUf ? governors[panelUf] : null;
  const panelPoliticos = panelUf ? politicosByUf[panelUf] : null;
  const hoverPoliticos = hover?.uf ? politicosByUf[hover.uf] : null;
  const tone = panelVar
    ? variationTone(panelVar.direction, indicator.higherIsBetter)
    : "neutral";

  const bands = useMemo(() => {
    if (!sel) return [];
    return administrations
      .filter((a) => (a.state_code || "").toUpperCase() === sel)
      .sort((a, b) =>
        String(a.start_date || "").localeCompare(String(b.start_date || ""))
      );
  }, [administrations, sel]);

  const yearIdx = years.indexOf(year);
  const prevY = yearIdx > 0 ? years[yearIdx - 1] : null;
  const nextY =
    yearIdx >= 0 && yearIdx < years.length - 1 ? years[yearIdx + 1] : null;
  const minY = years[0] ?? 2000;
  const maxY = years[years.length - 1] ?? 2026;

  function selectUf(uf: string) {
    const next = sel === uf ? null : uf;
    setSel(next);
    router.replace(
      href({
        ...qsBase,
        ano: year,
        sel: next,
      }),
      { scroll: false }
    );
  }

  function goYear(y: number) {
    if (y === year) return;
    setPlaying(false);
    router.push(yearHref(qsBase, y));
  }

  function onCategory(catId: string) {
    const cat = availableCats.find((c) => c.id === catId);
    const ind = cat?.indicators[0];
    if (!cat || !ind) return;
    router.push(
      href({
        layer: cat.layer,
        cat: cat.id,
        ind: ind.id,
        ano: year,
        nivel: ind.levels.includes("MUNICIPALITY") ? nivel : "STATE",
        uf: ufFilter,
        sel,
      })
    );
  }

  return (
    <div className="atlas-explorer" data-domain={categoryId}>
      <header className="atlas-explorer-head">
        <p className="eyebrow">Território · tempo · sociedade</p>
        <h1 className="atlas-explorer-title">Como o Brasil mudou?</h1>
        <p className="atlas-explorer-lede">
          Explore a evolução dos principais indicadores sociais e econômicos ao
          longo do tempo.
        </p>
      </header>

      <div className="atlas-cat-tabs" role="tablist" aria-label="Categorias">
        {availableCats.map((c) => (
          <button
            key={c.id}
            type="button"
            role="tab"
            aria-selected={categoryId === c.id}
            className={`atlas-cat-tab${categoryId === c.id ? " active" : ""}`}
            style={
              categoryId === c.id
                ? {
                    borderColor: domainHex(c.id),
                    color: domainHex(c.id),
                  }
                : undefined
            }
            onClick={() => onCategory(c.id)}
          >
            {c.label}
          </button>
        ))}
      </div>

      <form method="get" action="/indicadores" className="atlas-toolbar">
        <input type="hidden" name="camada" value={layer} />
        <input type="hidden" name="cat" value={categoryId} />
        <input type="hidden" name="ano" value={year} />
        {sel ? <input type="hidden" name="sel" value={sel} /> : null}
        {nivel === "MUNICIPALITY" ? (
          <input type="hidden" name="uf" value={ufFilter} />
        ) : null}

        <label className="atlas-field">
          <span>Indicador</span>
          <select
            name="ind"
            value={indicator.id}
            onChange={(e) => {
              const def = ALL_ATLAS_INDICATORS.find(
                (i) => i.id === e.target.value
              );
              router.push(
                href({
                  layer,
                  cat: categoryId,
                  ind: e.target.value,
                  ano: year,
                  nivel: def?.levels.includes("MUNICIPALITY")
                    ? nivel
                    : "STATE",
                  uf: ufFilter,
                  sel,
                })
              );
            }}
          >
            {(currentCat?.indicators || []).map((i) => (
              <option key={i.id} value={i.id}>
                {i.label}
              </option>
            ))}
          </select>
        </label>

        <label className="atlas-field">
          <span>Território</span>
          <select
            name="nivel"
            value={nivel}
            disabled={!indicator.levels.includes("MUNICIPALITY")}
            onChange={(e) =>
              router.push(
                href({
                  layer,
                  cat: categoryId,
                  ind: indicator.id,
                  ano: year,
                  nivel: e.target.value,
                  uf: ufFilter,
                  sel,
                })
              )
            }
          >
            <option value="STATE">Estados</option>
            {indicator.levels.includes("MUNICIPALITY") ? (
              <option value="MUNICIPALITY">Municípios</option>
            ) : null}
          </select>
        </label>

        <noscript>
          <button className="btn" type="submit">
            Aplicar
          </button>
        </noscript>
      </form>

      {categoryNote ? <p className="prose-note">{categoryNote}</p> : null}

      {!years.length ? (
        <section className="panel">
          <p className="muted">
            Sem observações para este indicador. Rode{" "}
            <code>python pipelines/run_indicadores.py</code>.
          </p>
        </section>
      ) : (
        <>
          {nivel === "STATE" ? (
            indicator.id === "ind_renuncia_fiscal" ? (
              <div className="atlas-stage atlas-stage-national">
                <section className="panel stack">
                  <p className="eyebrow">Agregado Brasil · federal</p>
                  <h2>Renúncia fiscal</h2>
                  <p className="atlas-side-value">
                    {liveSeries.find((p) => p.year === year)?.value != null
                      ? formatIndicatorValue(
                          indicator.id,
                          liveSeries.find((p) => p.year === year)!.value
                        )
                      : "—"}
                  </p>
                  <p className="muted">
                    Série nacional (RFB). Não há choropleth por UF nesta fonte.
                    Renúncia ≠ pagamento público.
                  </p>
                  <div className="chips">
                    <Link
                      className="chip"
                      href={`/contas?year=${year}&tab=renuncias`}
                    >
                      Ver para quem (beneficiários)
                    </Link>
                    <Link className="chip" href={`/contas?year=${year}&tab=resumo`}>
                      Contas · resumo
                    </Link>
                  </div>
                </section>
                <aside className="atlas-side">
                  <p className="eyebrow">{year}</p>
                  <h2>Brasil</h2>
                  <p className="faint">{indicator.label}</p>
                  <p className="prose-note">
                    Beneficiários identificados por CNPJ raiz / razão social na
                    fonte — não é lista de “favorecidos” inventada pelo Atlas.
                  </p>
                </aside>
              </div>
            ) : (
            <div className="atlas-stage">
              <div className="atlas-map-wrap">
                <AtlasMap
                  year={year}
                  values={values}
                  indicatorId={indicator.id}
                  unitLabel={indicator.unitLabel}
                  domainHex={domain}
                  higherIsBetter={indicator.higherIsBetter}
                  selectedUf={sel}
                  governors={governors}
                  onSelect={selectUf}
                  onHover={setHover}
                />
                {hover && hover.uf !== sel ? (
                  <div
                    className="atlas-map-tip"
                    style={{
                      left: Math.min(hover.x + 14, 420),
                      top: Math.max(8, hover.y - 12),
                    }}
                  >
                    <strong>
                      {BR_STATE_BY_UF[hover.uf]?.nome || hover.uf}
                    </strong>
                    <span>
                      {values[hover.uf] != null
                        ? formatIndicatorValue(indicator.id, values[hover.uf])
                        : "sem dado"}
                    </span>
                    {hoverPoliticos?.total ? (
                      <div className="atlas-tip-politicos">
                        <span className="atlas-tip-meta">
                          {hoverPoliticos.total} político(s) no corte Atlas
                        </span>
                        <ul>
                          {TIP_CLASSES.map((c) => {
                            const n = hoverPoliticos.byClass[c];
                            if (!n) return null;
                            return (
                              <li key={c}>
                                {POLITICO_CLASSE_LABEL[c]}: <strong>{n}</strong>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    ) : (
                      <span className="atlas-tip-meta">
                        Sem bancada Atlas neste UF
                      </span>
                    )}
                    {governors[hover.uf]?.name ? (
                      <>
                        <em className="atlas-tip-gov">
                          {governors[hover.uf]?.name}
                        </em>
                        <span className="atlas-tip-meta">
                          Governador(a) em {year}
                          {governors[hover.uf]?.party
                            ? ` · ${governors[hover.uf]?.party}`
                            : ""}
                        </span>
                      </>
                    ) : (
                      <em>Sem titular documentado em {year}</em>
                    )}
                  </div>
                ) : null}
              </div>

              <aside className="atlas-side">
                {panelUf && panelNome ? (
                  <>
                    <p className="eyebrow">{year}</p>
                    <h2>{panelNome}</h2>
                    <p className="atlas-side-value">
                      {panelVal != null
                        ? formatIndicatorValue(indicator.id, panelVal)
                        : "—"}
                    </p>
                    <p className="faint">{indicator.label}</p>

                    <dl className="atlas-stats">
                      {brasil != null ? (
                        <div>
                          <dt>Brasil</dt>
                          <dd>
                            {formatIndicatorValue(indicator.id, brasil)}
                            <span className="faint">
                              {" "}
                              ({indicator.aggregation === "sum"
                                ? "soma"
                                : "média"}{" "}
                              das UFs)
                            </span>
                          </dd>
                        </div>
                      ) : null}
                      {panelRank ? (
                        <div>
                          <dt>Posição</dt>
                          <dd>
                            {panelRank.rank}º de {panelRank.total}
                            {indicator.higherIsBetter
                              ? " (maior valor)"
                              : " (menor valor)"}
                          </dd>
                        </div>
                      ) : null}
                      {panelVar && prevYear ? (
                        <div>
                          <dt>Desde {prevYear}</dt>
                          <dd className={`atlas-var atlas-var-${tone}`}>
                            {panelVar.label}
                          </dd>
                        </div>
                      ) : null}
                    </dl>

                    <div className="atlas-gov-card">
                      <p className="eyebrow">Governo no período</p>
                      {panelGov?.name ? (
                        <>
                          <p className="item-title">{panelGov.name}</p>
                          <p className="item-meta">
                            {[panelGov.party, `${panelGov.start || "?"} — ${panelGov.end || "…"}`]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                        </>
                      ) : (
                        <p className="muted">
                          Sem administração estadual documentada para {year}.
                        </p>
                      )}
                      <p className="prose-note">
                        Indicadores observados durante o período administrativo
                        selecionado — não é desempenho do governador.
                      </p>
                    </div>

                    <div className="chips">
                      {panelGov?.personId ? (
                        <Link className="chip" href={`/pessoas/${panelGov.personId}`}>
                          Ver perfil
                        </Link>
                      ) : null}
                      <Link
                        className="chip"
                        href={`/territorios/${panelUf}?ano=${year}`}
                      >
                        Ver território
                      </Link>
                      <Link
                        className="chip"
                        href={`/indicadores/uf/${panelUf}?ind=${indicator.id}&ano=${year}`}
                      >
                        Ver governo
                      </Link>
                      <Link className="chip" href={`/contas?uf=${panelUf}&ano=${year}`}>
                        Contas públicas
                      </Link>
                    </div>

                    <PoliticosUfPanel
                      uf={panelUf}
                      ufNome={panelNome}
                      summary={panelPoliticos}
                      compact
                    />
                  </>
                ) : (
                  <>
                    <p className="eyebrow">Explore o mapa</p>
                    <h2>Passe o mouse ou clique um estado</h2>
                    <p className="muted">
                      No hover: indicador + quantos deputados federais,
                      senadores e governador(a) o Atlas tem naquele UF (bancada
                      federal — sem AL/prefeituras ainda). No clique: amostra de
                      políticos do estado.
                    </p>
                    {brasil != null ? (
                      <p className="atlas-side-value">
                        {formatIndicatorValue(indicator.id, brasil)}
                      </p>
                    ) : null}
                    <p className="faint">
                      {indicator.label} · Brasil · {year}
                    </p>
                  </>
                )}
              </aside>
            </div>
            )
          ) : (
            <section className="panel stack">
              <p className="atlas-breadcrumb">
                Brasil → {BR_STATE_BY_UF[ufFilter]?.nome || ufFilter}
              </p>
              <p className="muted">
                Município ainda entra pela lista. Ao abrir um município, você
                vê a bancada federal do estado (deputados federais / senadores /
                governador) — não há coleta de prefeitos nem deputados
                estaduais ainda.
              </p>
              {governors[ufFilter]?.name ? (
                <p className="item-meta">
                  Governador em {year}: <strong>{governors[ufFilter]?.name}</strong>
                </p>
              ) : null}
              <PoliticosUfPanel
                uf={ufFilter}
                ufNome={BR_STATE_BY_UF[ufFilter]?.nome}
                summary={politicosByUf[ufFilter]}
              />
              <div className="chips">
                {BR_STATE_PATHS.map((s) => (
                  <Link
                    key={s.uf}
                    className={`chip${ufFilter === s.uf ? " active" : ""}`}
                    href={href({
                      layer,
                      cat: categoryId,
                      ind: indicator.id,
                      ano: year,
                      nivel: "MUNICIPALITY",
                      uf: s.uf,
                      sel: s.uf,
                    })}
                  >
                    {s.uf}
                  </Link>
                ))}
              </div>
              <div className="list-block">
                {munRows.map((row, i) => (
                  <Link
                    key={row.id}
                    href={`/indicadores/municipio/${row.id.replace(/^mun_/, "")}?ind=${indicator.id}&uf=${ufFilter}`}
                    className="list-item"
                  >
                    <p className="item-title">
                      #{i + 1} {row.name}
                    </p>
                    <p className="item-meta">
                      {formatIndicatorValue(indicator.id, row.value)}
                      {row.ibge ? ` · IBGE ${row.ibge}` : ""}
                      {" · políticos do estado →"}
                    </p>
                  </Link>
                ))}
                {!munRows.length ? (
                  <p className="muted">
                    Sem observação municipal para {ufFilter}/{year}.
                  </p>
                ) : null}
              </div>
            </section>
          )}

          <section className="atlas-timeline" aria-label="Linha do tempo">
            <div className="atlas-timeline-head">
              <p className="eyebrow">Ano de referência</p>
              <strong className="atlas-timeline-year">{year}</strong>
            </div>

            <div className="atlas-timeline-track">
              <div className="atlas-timeline-years" aria-hidden="true">
                {years
                  .filter(
                    (y, i, a) =>
                      i === 0 || i === a.length - 1 || y % 5 === 0 || y === year
                  )
                  .map((y) => {
                    const left =
                      ((y - minY) / Math.max(1, maxY - minY)) * 100;
                    return (
                      <button
                        key={y}
                        type="button"
                        className={`atlas-year-tick${y === year ? " current" : ""}`}
                        style={{ left: `${left}%` }}
                        onClick={() => goYear(y)}
                      >
                        {y}
                      </button>
                    );
                  })}
              </div>

              <div className="atlas-timeline-rail">
                <div
                  className="atlas-timeline-fill"
                  style={{
                    width: `${((year - minY) / Math.max(1, maxY - minY)) * 100}%`,
                  }}
                />
                <div
                  className="atlas-timeline-playhead"
                  style={{
                    left: `${((year - minY) / Math.max(1, maxY - minY)) * 100}%`,
                  }}
                  aria-hidden="true"
                />
                <input
                  type="range"
                  className="atlas-timeline-range"
                  min={minY}
                  max={maxY}
                  step={1}
                  value={year}
                  aria-label="Ano de referência"
                  onChange={(e) => {
                    const raw = Number(e.target.value);
                    // encaixa no ano disponível mais próximo
                    let best = years[0] ?? raw;
                    let dist = Math.abs(best - raw);
                    for (const y of years) {
                      const d = Math.abs(y - raw);
                      if (d < dist) {
                        best = y;
                        dist = d;
                      }
                    }
                    if (best !== year) goYear(best);
                  }}
                />
              </div>

              <div className="atlas-gov-bands">
                {sel && bands.length ? (
                  <>
                    {bands.map((a) => {
                      const y0 = Number(
                        String(a.start_date || minY).slice(0, 4)
                      );
                      const y1 = a.end_date
                        ? Number(String(a.end_date).slice(0, 4))
                        : maxY;
                      const left =
                        ((y0 - minY) / Math.max(1, maxY - minY)) * 100;
                      const width =
                        ((Math.max(y1, y0 + 1) - y0) /
                          Math.max(1, maxY - minY)) *
                        100;
                      const now = yearInAdminRange(
                        year,
                        a.start_date,
                        a.end_date
                      );
                      return (
                        <div
                          key={a.administration_id}
                          className={`atlas-gov-band${now ? " current" : ""}`}
                          style={{
                            left: `${Math.max(0, left)}%`,
                            width: `${Math.min(100 - left, Math.max(width, 4))}%`,
                          }}
                          title={`${a.executive_person_name || "Titular"} ${a.start_date || ""}–${a.end_date || ""}`}
                        >
                          {a.executive_person_name ||
                            a.party_at_start ||
                            "Governo"}
                        </div>
                      );
                    })}
                    <div
                      className="atlas-gov-yearline"
                      style={{
                        left: `${((year - minY) / Math.max(1, maxY - minY)) * 100}%`,
                      }}
                      aria-hidden="true"
                    />
                  </>
                ) : (
                  <p className="faint">
                    {sel
                      ? "Sem faixa de mandatos para este estado na base."
                      : "Clique um estado para ver a faixa dos governos sobre o tempo."}
                  </p>
                )}
              </div>
            </div>

            <div className="atlas-timeline-nav">
              {prevY ? (
                <button type="button" className="chip" onClick={() => goYear(prevY)}>
                  ◀ anterior
                </button>
              ) : (
                <span className="chip faint">◀ anterior</span>
              )}
              <button
                type="button"
                className={`chip${playing ? " active" : ""}`}
                onClick={() => setPlaying((p) => !p)}
              >
                {playing ? "■ pausar" : "▶ reproduzir"}
              </button>
              {nextY ? (
                <button type="button" className="chip" onClick={() => goYear(nextY)}>
                  próximo ▶
                </button>
              ) : (
                <span className="chip faint">próximo ▶</span>
              )}
            </div>
          </section>

          <section className="atlas-evo panel stack">
            <h2>Evolução histórica</h2>
            {sel ? (
              <p className="faint">
                {BR_STATE_BY_UF[sel]?.nome} · {indicator.label}
              </p>
            ) : (
              <p className="faint">
                Série do estado selecionado. Sem seleção, o gráfico espera um
                clique no mapa.
              </p>
            )}
            {liveSeries.length > 1 ? (
              <Sparkline
                points={liveSeries}
                year={year}
                indicatorId={indicator.id}
              />
            ) : (
              <p className="muted">Série insuficiente para o gráfico.</p>
            )}
            {sel && bands.length ? (
              <p className="faint">
                Faixas no gráfico acompanham os mandatos — observação
                temporal, não atribuição causal.
              </p>
            ) : null}
          </section>

          <section className="atlas-context panel stack">
            <h2>Contexto</h2>
            <p>
              {panelUf && panelVal != null && panelPrev != null && prevYear
                ? `Durante o recorte ${prevYear}–${year}, ${panelNome} passou de ${formatIndicatorValue(indicator.id, panelPrev)} para ${formatIndicatorValue(indicator.id, panelVal)}.`
                : `Indicador ${indicator.label} em ${year}.`}{" "}
              Isso representa evolução temporal e não atribuição causal ao
              governo.
            </p>
            {description ? <p className="muted">{description}</p> : null}
            <div className="chips">
              {sel ? (
                <Link className="chip" href={`/territorios/${sel}?ano=${year}`}>
                  Ver território
                </Link>
              ) : null}
              {sel ? (
                <Link
                  className="chip"
                  href={`/indicadores/uf/${sel}?ind=${indicator.id}&ano=${year}`}
                >
                  Ver governo
                </Link>
              ) : null}
              <Link
                className="chip"
                href={sel ? `/contas?uf=${sel}&ano=${year}` : "/contas"}
              >
                Ver contas públicas
              </Link>
              {methodologyUrl ? (
                <a
                  className="chip"
                  href={methodologyUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  Fonte{datasetId ? ` · ${datasetId}` : ""}
                </a>
              ) : (
                <span className="chip faint">
                  Fonte{datasetId ? ` · ${datasetId}` : ""}
                </span>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Sparkline({
  points,
  year,
  indicatorId,
}: {
  points: SeriesPoint[];
  year: number;
  indicatorId: string;
}) {
  const w = 640;
  const h = 160;
  const pad = 28;
  const xs = points.map((p) => p.year);
  const ys = points.map((p) => p.value);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const sx = (x: number) =>
    pad + ((x - minX) / Math.max(1, maxX - minX)) * (w - pad * 2);
  const sy = (v: number) =>
    h - pad - ((v - minY) / Math.max(1e-9, maxY - minY)) * (h - pad * 2);
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${sx(p.year)} ${sy(p.value)}`)
    .join(" ");
  const now = points.find((p) => p.year === year) || points[points.length - 1];

  return (
    <svg className="atlas-spark" viewBox={`0 0 ${w} ${h}`} role="img">
      <line
        x1={sx(year)}
        x2={sx(year)}
        y1={pad - 8}
        y2={h - pad + 4}
        className="atlas-spark-yearline"
      />
      <path d={d} fill="none" stroke="#a47b32" strokeWidth="2.2" />
      {now ? (
        <circle cx={sx(now.year)} cy={sy(now.value)} r="4.5" fill="#faf8f2" />
      ) : null}
      <text x={pad} y={16} className="atlas-spark-lab">
        {formatIndicatorValue(indicatorId, Math.max(...ys))}
      </text>
      <text x={pad} y={h - 6} className="atlas-spark-lab">
        {minX}
      </text>
      <text x={w - pad} y={h - 6} textAnchor="end" className="atlas-spark-lab">
        {maxX}
      </text>
      <text
        x={sx(year)}
        y={pad - 12}
        textAnchor="middle"
        className="atlas-spark-lab"
      >
        {year}
      </text>
    </svg>
  );
}
