import Link from "next/link";
import { notFound } from "next/navigation";
import { formatBRL } from "@/lib/format";
import { fetchMagistradoDetail } from "@/lib/magistrados";

function Sparkline({
  values,
  labels,
}: {
  values: number[];
  labels: string[];
}) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = Math.max(1, max - min);
  const w = 320;
  const h = 72;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / span) * (h - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <div className="atlas-spark">
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img">
        <polyline
          fill="none"
          stroke="var(--atlas-green)"
          strokeWidth="2"
          points={pts}
        />
      </svg>
      <div className="atlas-chart-axis faint">
        <span>{labels[0]}</span>
        <span>bruto por competência</span>
        <span>{labels[labels.length - 1]}</span>
      </div>
    </div>
  );
}

export default async function MagistradoPage({
  params,
}: {
  params: { id: string };
}) {
  const data = await fetchMagistradoDetail(params.id);
  if (!data?.magistrado) notFound();
  const m = data.magistrado;
  const comps = [...(data.compensations || [])].reverse();
  const series = comps
    .map((c) => ({
      label: String(
        c.reference_period || `${c.reference_year}-${c.reference_month}`
      ),
      gross: Number(c.gross_total),
    }))
    .filter((x) => Number.isFinite(x.gross));

  return (
    <div className="stack">
      <p className="eyebrow">
        <Link href="/magistrados">Magistrados</Link>
        {" · "}
        <Link href="/contas?tab=custo-judiciario">Custo judiciário</Link>
      </p>
      <h1 className="section-title">
        {String(m.display_name || m.normalized_name || m.magistrate_id)}
      </h1>
      <p className="muted">
        {[m.court_id, m.position].filter(Boolean).join(" · ")}
      </p>
      <p className="prose-note">{data.disclaimer}</p>

      {series.length >= 2 ? (
        <section className="panel stack">
          <h2>Série · bruto</h2>
          <Sparkline
            values={series.map((s) => s.gross)}
            labels={series.map((s) => s.label)}
          />
          <p className="faint">
            Último: {formatBRL(series[series.length - 1]?.gross)} · primeiro na
            amostra: {formatBRL(series[0]?.gross)}
          </p>
        </section>
      ) : null}

      <section className="panel stack">
        <h2>Competências (amostra)</h2>
        <div className="list-block">
          {[...(data.compensations || [])].map((c) => (
            <div key={String(c.id)} className="list-item">
              <span className="item-title">
                {String(
                  c.reference_period ||
                    `${c.reference_year}-${c.reference_month}`
                )}
              </span>
              <span className="item-meta">
                bruto {formatBRL(c.gross_total as number)} · líquido{" "}
                {formatBRL(c.net_total as number)} · subsídio{" "}
                {formatBRL(c.base_subsidy as number)}
              </span>
            </div>
          ))}
          {!comps.length ? (
            <p className="muted">Sem competências carregadas neste perfil.</p>
          ) : null}
        </div>
      </section>
      <p className="faint">Fonte: {data.source}</p>
    </div>
  );
}
