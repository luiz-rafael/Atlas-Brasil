import Link from "next/link";
import { notFound } from "next/navigation";
import {
  formatIndicatorValue,
  getCatalog,
  mandateYearRange,
  seriesDuringYears,
  seriesForTerritory,
  listYears,
} from "@/lib/indicators";
import { BR_STATE_PATHS } from "@/lib/br-states-paths";
import {
  fetchAdministrations,
  fetchTerritoryContext,
} from "@/lib/administrations";
import AtlasGovernmentContext from "@/components/AtlasGovernmentContext";
import AtlasTemporalSlider from "@/components/AtlasTemporalSlider";

const IND_CHIPS = [
  { id: "ind_pib_corrente", label: "PIB" },
  { id: "ind_pib_per_capita", label: "PIB per capita" },
  { id: "ind_pop_estimada", label: "População" },
  { id: "ind_ideb_anos_iniciais", label: "IDEB AI" },
  { id: "ind_ideb_anos_finais", label: "IDEB AF" },
  { id: "ind_ideb_ensino_medio", label: "IDEB EM" },
  { id: "ind_receita_bruta", label: "Receita" },
  { id: "ind_despesa_total", label: "Despesa" },
  { id: "ind_rcl", label: "RCL" },
  { id: "ind_despesa_saude", label: "Saúde $" },
  { id: "ind_despesa_educacao", label: "Educação $" },
  { id: "ind_despesa_saude_per_capita", label: "Saúde /hab" },
  { id: "ind_despesa_educacao_per_capita", label: "Educação /hab" },
  { id: "ind_mortalidade_infantil", label: "Mort. infantil" },
  { id: "ind_nascidos_vivos", label: "Nascimentos" },
  { id: "ind_obitos", label: "Óbitos" },
  { id: "ind_caged_saldo", label: "CAGED saldo" },
  { id: "ind_caged_admissoes", label: "CAGED adm." },
  { id: "ind_caged_desligamentos", label: "CAGED desl." },
] as const;

function resolveInd(raw?: string): string {
  return IND_CHIPS.some((c) => c.id === raw) ? (raw as string) : "ind_pib_corrente";
}

export default async function IndicadorUfPage({
  params,
  searchParams,
}: {
  params: { uf: string };
  searchParams?: { ind?: string; mandato?: string; ano?: string; adm?: string };
}) {
  const uf = (params.uf || "").toUpperCase();
  const nome = BR_STATE_PATHS.find((s) => s.uf === uf)?.nome;
  if (!nome) notFound();

  const indId = resolveInd(searchParams?.ind);
  const tid = `uf_${uf}`;

  const admins = await fetchAdministrations({ state_code: uf });
  const years = await listYears(indId);
  const latest = years[years.length - 1] || 2023;
  const ano = Math.min(
    latest,
    Math.max(
      years[0] || 2002,
      Number(searchParams?.ano || latest) || latest
    )
  );

  const ctx = await fetchTerritoryContext(tid, ano, [indId]);
  const adminAtYear = ctx?.administration || null;

  const selected =
    admins.find((a) => a.mandate_id === searchParams?.mandato) ||
    admins.find((a) => a.administration_id === searchParams?.adm) ||
    null;

  const range = selected
    ? mandateYearRange(selected.start_date, selected.end_date)
    : { from: null, toExclusive: null };

  const series =
    selected && range.from != null && range.toExclusive != null
      ? await seriesDuringYears(tid, indId, range.from, range.toExclusive)
      : await seriesForTerritory(tid, indId);
  const cat = await getCatalog();
  const terr = cat.territories.find((t) => t.territory_id === tid);
  const catalog = cat.indicators.find((i) => i.indicator_id === indId);
  const first = series[0];
  const last = series[series.length - 1];
  const delta =
    first && last && first.value
      ? ((last.value - first.value) / first.value) * 100
      : null;
  const max = Math.max(1, ...series.map((s) => s.value));
  const isIdeb = indId.startsWith("ind_ideb_");
  const qsInd = `ind=${indId}&ano=${ano}`;

  return (
    <div className="stack">
      <div>
        <p className="eyebrow">
          <Link href={`/indicadores?ano=${ano}&ind=${indId}`}>Indicadores</Link>{" "}
          · Estado
        </p>
        <h1 className="section-title">{nome}</h1>
        <p className="muted">
          IBGE {terr?.ibge_code || "—"} · região {terr?.region_name || "—"}
        </p>
        <p className="prose-note">
          {selected
            ? `Recorte da administração de ${selected.executive_person_name || "titular"} (${selected.start_date || "?"} → ${selected.end_date || "?"}). Variação no período ≠ causalidade.`
            : "Jornada mapa → ano → governo → indicadores → perfil. Observação territorial, não atribuição política."}
        </p>
      </div>

      <AtlasTemporalSlider
        years={years.filter((y) => y >= 2010 || y === years[0])}
        year={ano}
        basePath={`/indicadores/uf/${uf}`}
        preserve={{
          ind: indId,
          mandato: searchParams?.mandato,
          adm: searchParams?.adm,
        }}
      />

      <AtlasGovernmentContext
        year={ano}
        administration={adminAtYear}
        territoryLabel={nome}
      />

      <div className="chips">
        <Link className="chip" href={`/indicadores?ano=${ano}&ind=${indId}`}>
          ← Mapa
        </Link>
        <Link className="chip" href={`/contas?ano=${ano}`}>
          Contas (federal)
        </Link>
        {IND_CHIPS.map((c) => (
          <Link
            key={c.id}
            className={`chip${indId === c.id ? " active" : ""}`}
            href={`/indicadores/uf/${uf}?ind=${c.id}&ano=${ano}${
              selected?.mandate_id
                ? `&mandato=${encodeURIComponent(selected.mandate_id)}`
                : ""
            }`}
          >
            {c.label}
          </Link>
        ))}
      </div>

      {admins.length > 0 ? (
        <div className="chips">
          <Link
            className={`chip${!selected ? " active" : ""}`}
            href={`/indicadores/uf/${uf}?${qsInd}`}
          >
            Série completa
          </Link>
          {admins.map((m) => (
            <Link
              key={m.administration_id}
              className={`chip${
                selected?.administration_id === m.administration_id
                  ? " active"
                  : ""
              }`}
              href={`/indicadores/uf/${uf}?${qsInd}&adm=${encodeURIComponent(
                m.administration_id
              )}${
                m.mandate_id
                  ? `&mandato=${encodeURIComponent(m.mandate_id)}`
                  : ""
              }`}
              title={`${m.start_date || "?"} → ${m.end_date || "?"}`}
            >
              {(m.executive_person_name || "Gov")
                .split(" ")
                .slice(0, 2)
                .join(" ")}
              {m.election_year != null ? ` (${m.election_year})` : ""}
            </Link>
          ))}
        </div>
      ) : null}

      <section className="panel stack">
        <h2>{catalog?.display_name || indId}</h2>
        {!series.length ? (
          <p className="muted">
            {selected
              ? "Sem observações deste indicador no período da administração."
              : "Sem observações para esta UF."}
          </p>
        ) : (
          <>
            <p className="muted">
              {first?.reference_year}–{last?.reference_year}:{" "}
              {formatIndicatorValue(indId, first?.value || 0)} →{" "}
              {formatIndicatorValue(indId, last?.value || 0)}
              {delta != null
                ? ` (${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%${
                    isIdeb ? "" : " no período"
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
                  <span
                    className="mono item-meta"
                    style={{ width: 130, textAlign: "right" }}
                  >
                    {formatIndicatorValue(indId, o.value)}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
