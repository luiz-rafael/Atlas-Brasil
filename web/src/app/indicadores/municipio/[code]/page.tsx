import Link from "next/link";
import { notFound } from "next/navigation";
import {
  formatIndicatorValue,
  getCatalog,
  seriesForTerritory,
} from "@/lib/indicators";
import { fetchPessoasList } from "@/lib/pessoas";
import { buildPoliticosByUf } from "@/lib/politicos-by-uf";
import PoliticosUfPanel from "@/components/PoliticosUfPanel";
import { BR_STATE_BY_UF } from "@/lib/br-states-paths";

const IND_CHIPS = [
  { id: "ind_pib_corrente", label: "PIB" },
  { id: "ind_pib_per_capita", label: "PIB per capita" },
  { id: "ind_pop_estimada", label: "População" },
  { id: "ind_ideb_anos_iniciais", label: "IDEB AI" },
  { id: "ind_ideb_anos_finais", label: "IDEB AF" },
  { id: "ind_ideb_ensino_medio", label: "IDEB EM" },
  { id: "ind_receita_bruta", label: "Receita" },
  { id: "ind_despesa_total", label: "Despesa" },
  { id: "ind_despesa_saude", label: "Saúde $" },
  { id: "ind_despesa_educacao", label: "Educação $" },
  { id: "ind_despesa_pessoal", label: "Pessoal" },
  { id: "ind_despesa_investimentos", label: "Investimentos" },
  { id: "ind_mortalidade_infantil", label: "Mort. infantil" },
  { id: "ind_nascidos_vivos", label: "Nascimentos" },
  { id: "ind_obitos", label: "Óbitos" },
] as const;

function resolveInd(raw?: string): string {
  return IND_CHIPS.some((c) => c.id === raw) ? (raw as string) : "ind_pib_corrente";
}

export default async function IndicadorMunicipioPage({
  params,
  searchParams,
}: {
  params: { code: string };
  searchParams?: { ind?: string };
}) {
  const code = String(params.code || "").replace(/\D/g, "");
  if (!code) notFound();

  const tid = `mun_${code}`;
  const cat = await getCatalog();
  const terr = cat.territories.find((t) => t.territory_id === tid);
  if (!terr) notFound();

  const indId = resolveInd(searchParams?.ind);
  const series = await seriesForTerritory(tid, indId);
  const catalog = cat.indicators.find(
    (i) => i.indicator_id === indId
  );
  const first = series[0];
  const last = series[series.length - 1];
  const delta =
    first && last && first.value
      ? ((last.value - first.value) / first.value) * 100
      : null;
  const max = Math.max(1, ...series.map((s) => s.value));
  const uf = terr.state_code || "";
  const isIdeb = indId.startsWith("ind_ideb_");

  const pessoasUf = uf
    ? await fetchPessoasList({ no_poder: "sim", uf, limit: 500 })
    : null;
  const politicosSummary = uf
    ? buildPoliticosByUf(pessoasUf?.items || [], {
        onlyNoPoder: true,
        samplePerUf: 12,
      })[uf]
    : null;

  return (
    <div className="stack">
      <div>
        <p className="eyebrow">
          <Link href="/indicadores">Indicadores</Link> · Município
        </p>
        <h1 className="section-title">{terr.name}</h1>
        <p className="muted">
          IBGE {terr.ibge_code} · {terr.state_name || uf}
        </p>
        <p className="prose-note">
          {isIdeb
            ? "IDEB rede pública (INEP). Escala 0–10. Observação ≠ atribuição política."
            : "Observações IBGE / derivadas. PIB e PIB per capita em preços correntes (nominal). Observação ≠ atribuição política."}
        </p>
      </div>

      <div className="chips">
        <Link
          className="chip"
          href={`/indicadores?ind=${indId}&nivel=MUNICIPALITY&uf=${uf}`}
        >
          ← Lista {uf}
        </Link>
        {IND_CHIPS.map((c) => (
          <Link
            key={c.id}
            className={`chip${indId === c.id ? " active" : ""}`}
            href={`/indicadores/municipio/${code}?ind=${c.id}`}
          >
            {c.label}
          </Link>
        ))}
        {uf ? (
          <Link className="chip" href={`/indicadores/uf/${uf}?ind=${indId}`}>
            Estado {uf}
          </Link>
        ) : null}
      </div>

      <section className="panel stack">
        <h2>{catalog?.display_name || indId}</h2>
        {!series.length ? (
          <p className="muted">Sem observações para este município.</p>
        ) : (
          <>
            <p className="muted">
              {first?.reference_year}–{last?.reference_year}:{" "}
              {formatIndicatorValue(indId, first?.value || 0)} →{" "}
              {formatIndicatorValue(indId, last?.value || 0)}
              {delta != null
                ? ` (${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%${
                    isIdeb ? "" : " nominal"
                  })`
                : ""}
            </p>
            <div className="indicator-bars">
              {series.map((o) => (
                <div key={o.observation_id} className="indicator-bar-row">
                  <span className="faint" style={{ width: 48 }}>
                    {o.reference_year}
                  </span>
                  <div className="indicator-bar-track">
                    <div
                      className="indicator-bar-fill"
                      style={{ width: `${(o.value / max) * 100}%` }}
                    />
                  </div>
                  <span className="mono item-meta" style={{ width: 130, textAlign: "right" }}>
                    {formatIndicatorValue(indId, o.value)}
                  </span>
                </div>
              ))}
            </div>
            <p className="faint">
              Fonte:{" "}
              {isIdeb ? (
                <a
                  href="https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb"
                  target="_blank"
                  rel="noreferrer"
                >
                  INEP IDEB
                </a>
              ) : (
                <a
                  href="https://sidra.ibge.gov.br/tabela/5938"
                  target="_blank"
                  rel="noreferrer"
                >
                  IBGE SIDRA 5938
                </a>
              )}
            </p>
          </>
        )}
      </section>

      {uf ? (
        <section className="panel stack">
          <PoliticosUfPanel
            uf={uf}
            ufNome={BR_STATE_BY_UF[uf]?.nome || terr.state_name || uf}
            summary={politicosSummary}
          />
        </section>
      ) : null}
    </div>
  );
}
