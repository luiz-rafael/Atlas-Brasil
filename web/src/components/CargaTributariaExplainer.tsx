import Link from "next/link";
import { formatContasExact, formatContasValue } from "@/lib/format";
import type { CargaTributariaPoint } from "@/lib/contas";

function PctChart({ points }: { points: CargaTributariaPoint[] }) {
  const vals = points
    .map((p) => Number(p.pct_pib))
    .filter((n) => Number.isFinite(n));
  if (vals.length < 2) return null;
  const max = Math.max(...vals);
  const min = Math.min(...vals);
  const lo = Math.max(0, min - 2);
  const hi = max + 1;
  const span = Math.max(1, hi - lo);

  return (
    <div className="atlas-chart" role="img" aria-label="Carga tributária % PIB">
      <div className="atlas-chart-bars atlas-chart-bars-tall">
        {points.map((p) => {
          const v = Number(p.pct_pib);
          if (!Number.isFinite(v)) return null;
          const h = Math.max(4, Math.round(((v - lo) / span) * 100));
          return (
            <div key={p.year} className="atlas-chart-col">
              <div
                className="atlas-chart-bar"
                style={{ height: `${h}%` }}
                title={`${p.year}: ${v.toLocaleString("pt-BR", {
                  maximumFractionDigits: 1,
                })}% do PIB`}
              />
              <span className="atlas-chart-year">{p.year}</span>
            </div>
          );
        })}
      </div>
      <p className="faint atlas-chart-caption">
        % do PIB · escala relativa (mín. {min.toFixed(1)}% · máx.{" "}
        {max.toFixed(1)}%)
      </p>
    </div>
  );
}

function AmountChart({ points }: { points: CargaTributariaPoint[] }) {
  const vals = points
    .map((p) => Number(p.amount_brl))
    .filter((n) => Number.isFinite(n) && n > 0);
  if (vals.length < 2) return null;
  const max = Math.max(...vals);

  return (
    <div
      className="atlas-chart"
      role="img"
      aria-label="Arrecadação tributária bruta"
    >
      <div className="atlas-chart-bars atlas-chart-bars-tall">
        {points.map((p) => {
          const v = Number(p.amount_brl);
          if (!Number.isFinite(v) || v <= 0) return null;
          const h = Math.max(4, Math.round((v / max) * 100));
          return (
            <div key={p.year} className="atlas-chart-col">
              <div
                className="atlas-chart-bar atlas-chart-bar-gold"
                style={{ height: `${h}%` }}
                title={`${p.year}: ${formatContasValue(v, "BRL")}`}
              />
              <span className="atlas-chart-year">{p.year}</span>
            </div>
          );
        })}
      </div>
      <p className="faint atlas-chart-caption">
        Arrecadação tributária bruta associada (R$) — nominal
      </p>
    </div>
  );
}

/** Guia editorial: o que a carga tributária mede — e o que o brasileiro paga. */
export default function CargaTributariaExplainer({
  year,
  ratio,
  amountBrl,
  methodology,
  source,
  series = [],
  seriesNote,
}: {
  year: number;
  ratio?: number | null;
  amountBrl?: number | null;
  methodology?: string | null;
  source?: string | null;
  series?: CargaTributariaPoint[];
  seriesNote?: string | null;
}) {
  const pctLabel =
    ratio != null ? formatContasValue(ratio, "ratio") : "sem dado neste ano";
  const sorted = [...series].sort(
    (a, b) => Number(a.year || 0) - Number(b.year || 0)
  );

  return (
    <section className="atlas-carga stack">
      <header className="atlas-carga-hero">
        <p className="eyebrow">Contas · carga tributária</p>
        <h2 className="atlas-carga-title">O que o brasileiro paga?</h2>
        <p className="atlas-carga-lede">
          A carga tributária oficial não é o imposto do holerite — é a parcela
          do PIB que vira tributo (União, estados e municípios). Em {year}:{" "}
          <strong>{pctLabel}</strong>
          {amountBrl != null ? (
            <>
              {" "}
              · arrecadação bruta associada{" "}
              <strong title={formatContasExact(amountBrl, "BRL") || undefined}>
                {formatContasValue(amountBrl, "BRL")}
              </strong>
            </>
          ) : null}
          .
        </p>
      </header>

      {sorted.length >= 2 ? (
        <section className="panel stack">
          <h3>Ao longo do tempo · % do PIB</h3>
          <p className="muted">
            Indicador CTB (RFB):{" "}
            <code>ind_carga_tributaria_pib</code>. Use os anos no topo da página
            Contas para detalhar um ano.
          </p>
          <PctChart points={sorted} />
          <h3>Ao longo do tempo · arrecadação bruta (R$)</h3>
          <AmountChart points={sorted} />
          {seriesNote ? <p className="prose-note">{seriesNote}</p> : null}
          <div className="list-block">
            {[...sorted].reverse().map((p) => (
              <Link
                key={p.year}
                href={`/contas?year=${p.year}&tab=carga`}
                className="list-item"
              >
                <span className="item-title">{p.year}</span>
                <span className="item-meta">
                  {p.pct_pib != null
                    ? `${Number(p.pct_pib).toLocaleString("pt-BR", {
                        maximumFractionDigits: 1,
                      })}% do PIB`
                    : "—"}
                  {p.amount_brl != null
                    ? ` · ${formatContasValue(p.amount_brl, "BRL")}`
                    : ""}
                </span>
              </Link>
            ))}
          </div>
        </section>
      ) : (
        <p className="muted">
          Série temporal ainda não disponível neste serving. O valor do ano
          selecionado aparece acima, quando houver observação.
        </p>
      )}

      <div className="atlas-carga-grid">
        <article className="atlas-carga-card">
          <h3>1. O que a carga mede</h3>
          <p>
            Estudo <strong>Carga Tributária no Brasil (CTB)</strong> da Receita
            Federal: razão entre a arrecadação tributária bruta e o PIB. É um
            indicador macro — não o “quanto eu pago de IR”.
          </p>
          <p className="prose-note">
            Carga (% PIB) ≠ série de arrecadação federal nominal ≠ receita
            orçamentária do Tesouro (RTN).
          </p>
        </article>

        <article className="atlas-carga-card">
          <h3>2. O que entra no bolso do cidadão</h3>
          <ul className="atlas-carga-list">
            <li>
              <strong>Sobre a renda</strong> — IRPF, IRPJ e CSLL.
            </li>
            <li>
              <strong>Sobre o consumo</strong> — ICMS, ISS, IPI, PIS/COFINS
              embutidos no preço.
            </li>
            <li>
              <strong>Sobre o trabalho</strong> — contribuições previdenciárias
              (cobertura CTB varia por edição: FGTS / Sistema S).
            </li>
            <li>
              <strong>Patrimônio e outros</strong> — IPTU, IPVA, ITBI, IOF…
            </li>
          </ul>
        </article>

        <article className="atlas-carga-card">
          <h3>3. Quem cobra</h3>
          <ul className="atlas-carga-list">
            <li>
              <strong>União</strong> — IR, IPI, PIS/COFINS, IOF…
            </li>
            <li>
              <strong>Estados</strong> — ICMS, IPVA, ITCMD…
            </li>
            <li>
              <strong>Municípios</strong> — ISS, IPTU, ITBI…
            </li>
          </ul>
        </article>

        <article className="atlas-carga-card">
          <h3>4. O que a carga NÃO é</h3>
          <ul className="atlas-carga-list">
            <li>Não é a alíquota efetiva da sua família.</li>
            <li>Não é resultado primário/nominal do Tesouro.</li>
            <li>Não é renúncia fiscal.</li>
          </ul>
        </article>
      </div>

      {methodology ? (
        <p className="prose-note atlas-carga-method">
          Metodologia ({source || "fonte"}): {methodology}
        </p>
      ) : null}

      <div className="chips">
        <Link className="chip" href={`/contas?year=${year}&tab=resumo`}>
          Voltar ao resumo {year}
        </Link>
        <Link className="chip" href={`/contas?year=${year}&tab=renuncias`}>
          Renúncias (≠ pagamento)
        </Link>
        <a
          className="chip"
          href="https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/estudos/carga-tributaria"
          target="_blank"
          rel="noreferrer"
        >
          Estudo CTB (RFB)
        </a>
      </div>
    </section>
  );
}
