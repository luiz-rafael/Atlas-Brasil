import {
  getCatalog,
  listYears,
  observationsForYear,
  seriesForTerritory,
  ufValuesMap,
} from "@/lib/indicators";
import { fetchAdministrations } from "@/lib/administrations";
import { fetchContasRenunciasSeries } from "@/lib/contas";
import { fetchPessoasList } from "@/lib/pessoas";
import { buildPoliticosByUf } from "@/lib/politicos-by-uf";
import AtlasExplorer, {
  type AdminBand,
  type SeriesPoint,
} from "@/components/AtlasExplorer";
import type { GovernorOnMap } from "@/components/AtlasMap";
import {
  resolveAtlasSelection,
  type AtlasLayer,
} from "@/lib/indicator-taxonomy";

function prevAvailableYear(years: number[], ano: number): number | null {
  const earlier = years.filter((y) => y < ano);
  return earlier.length ? earlier[earlier.length - 1] : null;
}

export default async function IndicadoresPage({
  searchParams,
}: {
  searchParams?: {
    ano?: string;
    ind?: string;
    nivel?: string;
    uf?: string;
    sel?: string;
    camada?: string;
    cat?: string;
  };
}) {
  const { layer, category, indicator } = resolveAtlasSelection({
    layer: searchParams?.camada,
    cat: searchParams?.cat,
    ind: searchParams?.ind,
  });

  const isRenuncia = indicator.id === "ind_renuncia_fiscal";

  const nivel =
    searchParams?.nivel === "MUNICIPALITY" &&
    indicator.levels.includes("MUNICIPALITY")
      ? "MUNICIPALITY"
      : "STATE";
  const ufFilter = (searchParams?.uf || "MG").toUpperCase();
  const selectedUf = (searchParams?.sel || "").toUpperCase() || null;

  const cat = await getCatalog();

  let years: number[] = [];
  let series: SeriesPoint[] = [];
  if (isRenuncia) {
    const ren = await fetchContasRenunciasSeries(40);
    const points = (ren?.items || [])
      .map((row) => ({
        year: Number(row.year),
        value: Number(row.valor),
      }))
      .filter((p) => Number.isFinite(p.year) && Number.isFinite(p.value))
      .sort((a, b) => a.year - b.year);
    years = points.map((p) => p.year);
    series = points;
  } else {
    years = await listYears(indicator.id);
  }

  const latest = years[years.length - 1] || 2023;
  const ano = Math.min(
    latest,
    Math.max(years[0] || 2002, Number(searchParams?.ano || latest) || latest)
  );
  const prevYear = prevAvailableYear(years, ano);

  const catalog = cat.indicators.find((i) => i.indicator_id === indicator.id);

  const [values, prevValues, yearAdmins, allAdmins, pessoasList] =
    await Promise.all([
      !isRenuncia && nivel === "STATE"
        ? ufValuesMap(ano, indicator.id)
        : Promise.resolve({} as Record<string, number>),
      !isRenuncia && prevYear && nivel === "STATE"
        ? ufValuesMap(prevYear, indicator.id)
        : Promise.resolve({} as Record<string, number>),
      fetchAdministrations({ year: ano, limit: 80 }),
      fetchAdministrations({ limit: 400 }),
      fetchPessoasList({ no_poder: "sim", limit: 2000 }),
    ]);

  const politicosByUf = buildPoliticosByUf(pessoasList?.items || [], {
    onlyNoPoder: true,
    samplePerUf: 10,
  });

  const governors: Record<string, GovernorOnMap | null> = {};
  for (const a of yearAdmins) {
    const uf = (a.state_code || "").toUpperCase();
    if (uf.length !== 2) continue;
    governors[uf] = {
      name: a.executive_person_name || "",
      personId: a.executive_person_id,
      party: a.party_at_start,
      start: a.start_date,
      end: a.end_date,
    };
  }

  const administrations: AdminBand[] = (allAdmins.length ? allAdmins : yearAdmins)
    .filter((a) => (a.state_code || "").length === 2)
    .map((a) => ({
      administration_id: a.administration_id,
      state_code: a.state_code,
      executive_person_name: a.executive_person_name,
      party_at_start: a.party_at_start,
      start_date: a.start_date,
      end_date: a.end_date,
    }));

  if (!isRenuncia && selectedUf) {
    const obs = await seriesForTerritory(`uf_${selectedUf}`, indicator.id);
    series = obs.map((o) => ({ year: o.reference_year, value: o.value }));
  }

  const munObs =
    !isRenuncia && nivel === "MUNICIPALITY"
      ? await observationsForYear(ano, indicator.id, {
          level: "MUNICIPALITY",
          uf: ufFilter,
        })
      : [];
  const munRows = munObs
    .map((o) => {
      const t = cat.territories.find((x) => x.territory_id === o.territory_id);
      return {
        id: o.territory_id,
        name: t?.name || o.territory_id,
        ibge: t?.ibge_code,
        value: o.value,
      };
    })
    .sort((a, b) => b.value - a.value)
    .slice(0, 40);

  return (
    <AtlasExplorer
      layer={layer as AtlasLayer}
      categoryId={category.id}
      indicator={indicator}
      categoryNote={category.note}
      year={ano}
      years={years}
      nivel={nivel}
      ufFilter={ufFilter}
      selectedUf={selectedUf}
      values={values}
      prevValues={prevValues}
      prevYear={prevYear}
      governors={governors}
      administrations={administrations}
      series={series}
      methodologyUrl={catalog?.methodology_url}
      datasetId={catalog?.dataset_id || "rfb.renuncias"}
      description={
        catalog?.description ||
        (isRenuncia
          ? "Soma anual de benefícios/renúncias fiscais federais (RFB). Renúncia ≠ pagamento."
          : undefined)
      }
      munRows={munRows}
      politicosByUf={politicosByUf}
    />
  );
}
