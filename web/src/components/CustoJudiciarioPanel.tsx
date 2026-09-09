import Link from "next/link";
import { formatBRL, formatContasValue } from "@/lib/format";
import type { MagStats } from "@/lib/magistrados";

function BarChart({
  points,
  valueKey,
  label,
}: {
  points: Array<{ period?: string; [k: string]: unknown }>;
  valueKey: string;
  label: string;
}) {
  const vals = points
    .map((p) => Number(p[valueKey]))
    .filter((n) => Number.isFinite(n) && n > 0);
  const max = Math.max(1, ...vals);
  const slice = points.filter((p) => Number(p[valueKey]) > 0).slice(-36);

  if (!slice.length) {
    return <p className="muted">Sem pontos para o gráfico ({label}).</p>;
  }

  return (
    <div className="atlas-chart" role="img" aria-label={label}>
      <div className="atlas-chart-bars">
        {slice.map((p, i) => {
          const v = Number(p[valueKey]) || 0;
          const h = Math.max(2, Math.round((v / max) * 100));
          return (
            <div
              key={`${p.period}-${i}`}
              className="atlas-chart-bar"
              title={`${p.period}: ${formatBRL(v)}`}
              style={{ height: `${h}%` }}
            />
          );
        })}
      </div>
      <div className="atlas-chart-axis faint">
        <span>{slice[0]?.period}</span>
        <span>{label}</span>
        <span>{slice[slice.length - 1]?.period}</span>
      </div>
    </div>
  );
}

export default function CustoJudiciarioPanel({
  stats,
  year,
  courtId,
}: {
  stats: MagStats | null;
  year?: number;
  courtId?: string;
}) {
  const timeline = stats?.timeline || [];
  const byCourt = stats?.by_court || [];
  const top = stats?.top_avg_gross || [];
  const latest = stats?.latest_period;
  const courts = stats?.courts || [];

  // Série anual (macro): soma gross por ano
  const byYearMap = new Map<number, number>();
  for (const p of timeline) {
    const y = Number(p.year);
    if (!y || p.sum_gross == null) continue;
    byYearMap.set(y, (byYearMap.get(y) || 0) + Number(p.sum_gross));
  }
  const annual = Array.from(byYearMap.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([y, sum_gross]) => ({ period: String(y), sum_gross }));

  return (
    <section className="atlas-custo-jud stack">
      <header className="atlas-carga-hero">
        <p className="eyebrow">Contas · custo judiciário</p>
        <h2 className="atlas-carga-title">Remuneração do Judiciário</h2>
        <p className="atlas-carga-lede">
          Análise a partir da transparência CNJ (folha de magistrados). Isto{" "}
          <strong>não</strong> é o orçamento total dos tribunais nem o custo por
          processo — é a soma das remunerações publicadas na cobertura Atlas.
        </p>
      </header>

      <p className="prose-note">
        {stats?.coverage_note ||
          "Cobertura parcial. Remuneração pública ≠ culpa ou irregularidade."}
      </p>
      <p className="prose-note">{stats?.disclaimer}</p>

      {!stats?.ok ? (
        <p className="muted">
          Agregados indisponíveis
          {stats?.error ? ` (${stats.error})` : ""}. Confira Postgres + load de
          magistrados.
        </p>
      ) : (
        <>
          <form className="filters atlas-money-filters" method="get">
            <input type="hidden" name="tab" value="custo-judiciario" />
            <select name="court" defaultValue={courtId || ""}>
              <option value="">Todos os tribunais (cobertura)</option>
              {courts.map((c) => (
                <option key={c.court_id} value={c.court_id}>
                  {c.court_id.toUpperCase()} · {c.magistrates} magistrados
                </option>
              ))}
            </select>
            <select name="jyear" defaultValue={year ? String(year) : ""}>
              <option value="">Série completa</option>
              {(stats.years || []).map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
            <button className="btn" type="submit">
              Filtrar
            </button>
            <Link className="chip" href="/magistrados">
              Lista individual →
            </Link>
          </form>

          <div className="atlas-money-grid">
            <div className="atlas-money-card">
              <div className="item-title">Tribunais na base</div>
              <div className="atlas-money-value">{courts.length}</div>
              <div className="item-meta muted">
                {courts.map((c) => c.court_id.toUpperCase()).join(" · ") || "—"}
              </div>
            </div>
            <div className="atlas-money-card">
              <div className="item-title">Magistrados</div>
              <div className="atlas-money-value">
                {courts
                  .reduce((a, c) => a + (c.magistrates || 0), 0)
                  .toLocaleString("pt-BR")}
              </div>
              <div className="item-meta muted">cadastro · cobertura parcial</div>
            </div>
            <div className="atlas-money-card">
              <div className="item-title">
                Bruto (último período
                {latest?.period ? ` · ${latest.period}` : ""})
              </div>
              <div
                className="atlas-money-value"
                title={
                  latest?.sum_gross != null
                    ? formatBRL(latest.sum_gross)
                    : undefined
                }
              >
                {formatContasValue(latest?.sum_gross, "BRL")}
              </div>
              <div className="item-meta muted">
                {latest?.n_magistrates
                  ? `${latest.n_magistrates} magistrados na competência`
                  : "sem snapshot"}
              </div>
            </div>
            <div className="atlas-money-card">
              <div className="item-title">Média bruta (último período)</div>
              <div className="atlas-money-value">
                {formatContasValue(latest?.avg_gross, "BRL")}
              </div>
              <div className="item-meta muted">
                líquido médio {formatContasValue(latest?.avg_net, "BRL")} ·
                subsídio médio{" "}
                {formatContasValue(latest?.avg_subsidy, "BRL")}
              </div>
            </div>
          </div>

          <section className="panel stack">
            <h3>Macro · timeline do bruto publicado</h3>
            <p className="muted">
              Soma mensal de <code>gross_total</code> nas competências
              carregadas
              {courtId ? ` · ${courtId.toUpperCase()}` : ""}
              {year ? ` · ${year}` : ""}.
            </p>
            <BarChart
              points={timeline as Array<Record<string, unknown>>}
              valueKey="sum_gross"
              label="bruto mensal (soma)"
            />
          </section>

          <section className="panel stack">
            <h3>Macro · total anual</h3>
            <BarChart
              points={annual}
              valueKey="sum_gross"
              label="bruto anual (soma)"
            />
          </section>

          <section className="panel stack">
            <h3>Por tribunal</h3>
            <div className="list-block">
              {byCourt.map((c) => (
                <div key={c.court_id} className="list-item atlas-rank-row">
                  <span className="atlas-rank-pos">
                    {c.court_id.toUpperCase()}
                  </span>
                  <span style={{ flex: 1 }}>
                    <span className="item-title">
                      {formatContasValue(c.sum_gross, "BRL")} bruto (soma
                      competências)
                    </span>
                    <span className="item-meta">
                      {c.n_magistrates?.toLocaleString("pt-BR")} magistrados ·
                      média {formatContasValue(c.avg_gross, "BRL")} · líquido
                      soma {formatContasValue(c.sum_net, "BRL")}
                    </span>
                  </span>
                  <Link
                    className="chip"
                    href={`/contas?tab=custo-judiciario&court=${c.court_id}${
                      year ? `&jyear=${year}` : ""
                    }`}
                  >
                    Filtrar
                  </Link>
                </div>
              ))}
              {!byCourt.length ? (
                <p className="muted">Sem agregados por tribunal.</p>
              ) : null}
            </div>
          </section>

          <section className="panel stack">
            <h3>
              Micro · maiores médias brutas
              {stats.top_year ? ` · ${stats.top_year}` : ""}
            </h3>
            <p className="prose-note">
              Ranking por média anual de gross_total — documentação pública, não
              acusação. gross ≠ subsídio.
            </p>
            <div className="list-block">
              {top.map((m, i) => (
                <Link
                  key={m.magistrate_id}
                  href={`/magistrados/${m.magistrate_id}`}
                  className="list-item atlas-rank-row"
                >
                  <span className="atlas-rank-pos">#{i + 1}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span className="item-title">
                      {m.display_name || m.magistrate_id}
                    </span>
                    <span className="item-meta">
                      {(m.court_id || "").toUpperCase()} · média bruta{" "}
                      {formatContasValue(m.avg_gross, "BRL")} · líquido{" "}
                      {formatContasValue(m.avg_net, "BRL")} · subsídio{" "}
                      {formatContasValue(m.avg_subsidy, "BRL")}
                      {m.n_months ? ` · ${m.n_months} mês(es)` : ""}
                    </span>
                  </span>
                </Link>
              ))}
              {!top.length ? (
                <p className="muted">Sem ranking neste recorte.</p>
              ) : null}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
