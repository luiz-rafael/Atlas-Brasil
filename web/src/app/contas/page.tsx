import Link from "next/link";
import CargaTributariaExplainer from "@/components/CargaTributariaExplainer";
import CustoJudiciarioPanel from "@/components/CustoJudiciarioPanel";
import {
  fetchContasCno,
  fetchContasDivida,
  fetchContasPessoal,
  fetchContasRenuncias,
  fetchContasResumo,
  fetchContasResultado,
  fetchCargaTributariaSeries,
  type ContasResumo,
} from "@/lib/contas";
import { fetchMagistradosStats } from "@/lib/magistrados";
import { formatContasExact, formatContasValue } from "@/lib/format";

export const dynamic = "force-dynamic";

const SECTIONS = [
  { id: "resumo", label: "Resumo" },
  { id: "carga", label: "Carga tributária" },
  { id: "custo-judiciario", label: "Custo judiciário" },
  { id: "resultado", label: "Resultado" },
  { id: "divida", label: "Dívida" },
  { id: "renuncias", label: "Renúncias" },
  { id: "pessoal", label: "Pessoal" },
  { id: "cno", label: "CNO (obras)" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

const YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024];

function MetricCard({
  title,
  value,
  unit,
  source,
  note,
}: {
  title: string;
  value?: number | null;
  unit?: string | null;
  source?: string | null;
  note?: string | null;
}) {
  const display = formatContasValue(value, unit);
  const exact = formatContasExact(value, unit);
  return (
    <div className="atlas-money-card">
      <div className="item-title">{title}</div>
      <div className="atlas-money-value" title={exact || undefined}>
        {display}
      </div>
      {exact && exact !== display ? (
        <div className="atlas-money-exact faint">{exact}</div>
      ) : null}
      <div className="item-meta muted">
        {[source, note].filter(Boolean).join(" · ") || "sem cobertura neste ano"}
      </div>
    </div>
  );
}

function metricFrom(
  block: ContasResumo["quanto_entrou"] | Record<string, unknown> | null | undefined
) {
  if (!block || typeof block !== "object") {
    return {
      value: null as number | null,
      unit: null as string | null,
      source: null as string | null,
      note: null as string | null,
    };
  }
  const b = block as Record<string, unknown>;
  if ("value" in b && (typeof b.value === "number" || b.value == null)) {
    return {
      value: b.value as number | null,
      unit: (b.unit as string) || null,
      source: (b.source as string) || null,
      note: (b.period as string) || (b.methodology as string) || null,
    };
  }
  const primary = b.primary_result as Record<string, unknown> | undefined;
  if (primary && typeof primary === "object" && "value" in primary) {
    return {
      value: primary.value as number | null,
      unit: (primary.unit as string) || null,
      source: (primary.source as string) || null,
      note: (b.period as string) || (primary.methodology as string) || "primary_result",
    };
  }
  const items = b.items as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(items) && items.length) {
    const first = items[0];
    return {
      value: (first.value as number) ?? null,
      unit: (first.unit as string) || null,
      source: (first.source as string) || null,
      note: `${String(first.debt_indicator || "dívida")} · ${String(first.period || "")}`,
    };
  }
  return { value: null, unit: null, source: null, note: null };
}

function Empty({ children }: { children: string }) {
  return <p className="muted">{children}</p>;
}

function qs(opts: {
  year: number;
  tab: string;
  q?: string;
  uf?: string;
  sort?: string;
}) {
  const p = new URLSearchParams();
  p.set("year", String(opts.year));
  p.set("tab", opts.tab);
  if (opts.q) p.set("q", opts.q);
  if (opts.uf) p.set("uf", opts.uf);
  if (opts.sort) p.set("sort", opts.sort);
  return `/contas?${p.toString()}`;
}

export default async function ContasPage({
  searchParams,
}: {
  searchParams: {
    year?: string;
    tab?: string;
    q?: string;
    uf?: string;
    sort?: string;
    court?: string;
    jyear?: string;
  };
}) {
  const year = Number(searchParams.year || "2024") || 2024;
  const tab = (SECTIONS.some((s) => s.id === searchParams.tab)
    ? searchParams.tab
    : "resumo") as SectionId;
  const q = (searchParams.q || "").trim().toLowerCase();
  const uf = (searchParams.uf || "").trim().toUpperCase();
  const sort = searchParams.sort === "asc" ? "asc" : "desc";
  const courtId = (searchParams.court || "").trim().toLowerCase() || undefined;
  const jyearRaw = searchParams.jyear;
  const magYear = jyearRaw ? Number(jyearRaw) || undefined : undefined;

  const resumo = await fetchContasResumo(year);
  const apiDown = !resumo || resumo.error === "postgres_unavailable";

  const divida =
    !apiDown && (tab === "divida" || tab === "resumo")
      ? await fetchContasDivida(year, 8)
      : null;
  const resultado =
    !apiDown && (tab === "resultado" || tab === "resumo")
      ? await fetchContasResultado(year, 8)
      : null;
  const renuncias =
    !apiDown && (tab === "renuncias" || tab === "resumo")
      ? await fetchContasRenuncias(year, 5, "aggregate")
      : null;
  const beneficiarios =
    !apiDown && tab === "renuncias"
      ? await fetchContasRenuncias(year, 80, "beneficiarios")
      : null;
  const pessoal =
    !apiDown && (tab === "pessoal" || tab === "resumo")
      ? await fetchContasPessoal(year, 15)
      : null;
  const cno =
    !apiDown && tab === "cno"
      ? await fetchContasCno({ limit: 40, uf: uf || undefined })
      : null;
  const magStats =
    tab === "custo-judiciario"
      ? await fetchMagistradosStats({
          court_id: courtId,
          year: magYear,
        })
      : null;
  const cargaSeries =
    tab === "carga" || tab === "resumo"
      ? await fetchCargaTributariaSeries()
      : null;

  const entrou = metricFrom(resumo?.quanto_entrou);
  const saiu = metricFrom(resumo?.quanto_saiu);
  const resultadoM = metricFrom(
    resumo?.resultado_fiscal as Record<string, unknown>
  );
  const dividaM = metricFrom(resumo?.divida as Record<string, unknown>);
  const renuncia = metricFrom(resumo?.renuncia_fiscal);
  const pessoalM = metricFrom(resumo?.pessoal);
  const carga = metricFrom(resumo?.carga_tributaria_pib);
  const cargaExtra = resumo?.carga_tributaria_pib;

  let benefRows = [...(beneficiarios?.items || [])];
  if (q) {
    benefRows = benefRows.filter((row) => {
      const blob = [
        row.razao_social,
        row.cnpj_raiz,
        row.tributo,
        row.company_id,
      ]
        .map((x) => String(x || "").toLowerCase())
        .join(" ");
      return blob.includes(q);
    });
  }
  benefRows.sort((a, b) => {
    const va = Number(a.valor) || 0;
    const vb = Number(b.valor) || 0;
    return sort === "asc" ? va - vb : vb - va;
  });

  return (
    <div className="page stack atlas-contas">
      <div>
        <h1 className="section-title">Contas do Brasil</h1>
        <p className="muted">
          Visão canônica de dinheiro público. Valores em mi / bi / tri — passe o
          mouse para o valor exato.
        </p>
        <p className="prose-note">
          {resumo?.disclaimer ||
            "O Atlas não acusa. O Atlas documenta. Renúncia ≠ pagamento. Não misturar DPF/DBGG/DLSP nem primário/nominal."}
        </p>
      </div>

      <div className="tabs" aria-label="Ano">
        {YEARS.map((y) => (
          <Link
            key={y}
            href={qs({ year: y, tab, q: searchParams.q, uf, sort })}
            className={y === year ? "active" : undefined}
          >
            {y}
          </Link>
        ))}
        <Link href="/dinheiro">Contratos / fluxos →</Link>
      </div>

      <div className="tabs" aria-label="Seções Contas">
        {SECTIONS.map((s) => (
          <Link
            key={s.id}
            href={qs({ year, tab: s.id })}
            className={tab === s.id ? "active" : undefined}
          >
            {s.label}
          </Link>
        ))}
      </div>

      {apiDown ? (
        <div className="list-block">
          <Empty>
            API Contas indisponível. Confira Postgres + atlas-api em localhost:8001
            (ATLAS_API_URL).
          </Empty>
        </div>
      ) : (
        <>
          {tab === "carga" ? (
            <CargaTributariaExplainer
              year={year}
              ratio={carga.value}
              amountBrl={
                typeof cargaExtra?.amount_brl === "number"
                  ? cargaExtra.amount_brl
                  : null
              }
              methodology={
                cargaExtra?.methodology ||
                (typeof carga.note === "string" ? carga.note : null)
              }
              source={carga.source}
              series={cargaSeries?.items || []}
              seriesNote={cargaSeries?.nota}
            />
          ) : null}

          {tab === "custo-judiciario" ? (
            <CustoJudiciarioPanel
              stats={magStats}
              year={magYear}
              courtId={courtId}
            />
          ) : null}

          {(tab === "resumo" || tab === "resultado") && (
            <div className="atlas-money-grid">
              <MetricCard title="Quanto entrou (União · RTN)" {...entrou} />
              <MetricCard title="Quanto saiu (União · RTN)" {...saiu} />
              <MetricCard title="Resultado fiscal (primário)" {...resultadoM} />
              <MetricCard title="Dívida (amostra estoque)" {...dividaM} />
              <MetricCard
                title="Renúncia fiscal"
                {...renuncia}
                note={
                  renuncia.note
                    ? `${renuncia.note} · Renúncia ≠ pagamento`
                    : "Renúncia ≠ pagamento"
                }
              />
              <MetricCard title="Pessoal (SICONFI)" {...pessoalM} />
              <MetricCard
                title="Carga tributária"
                {...carga}
                note={
                  carga.note
                    ? `${carga.note} · ≠ arrecadação nominal`
                    : "≠ arrecadação nominal RFB"
                }
              />
              {tab === "resumo" ? (
                <div className="atlas-money-card atlas-money-card-link">
                  <div className="item-title">Entender a carga</div>
                  <p className="muted">
                    O que o brasileiro paga — renda, consumo, trabalho e o que a
                    CTB não mede.
                  </p>
                  <Link className="btn" href={qs({ year, tab: "carga" })}>
                    Guia da carga tributária
                  </Link>
                </div>
              ) : null}
              {tab === "resumo" ? (
                <div className="atlas-money-card atlas-money-card-link">
                  <div className="item-title">Custo judiciário</div>
                  <p className="muted">
                    Remuneração de magistrados (CNJ) — timeline, tribunais e
                    ranking individual.
                  </p>
                  <Link
                    className="btn"
                    href={qs({ year, tab: "custo-judiciario" })}
                  >
                    Ver análise
                  </Link>
                </div>
              ) : null}
            </div>
          )}

          {(tab === "resumo" || tab === "resultado") && (
            <section className="stack">
              <h2 className="section-title">Resultado fiscal (amostra {year})</h2>
              <div className="list-block">
                {(resultado?.items || []).length === 0 && (
                  <Empty>{`Sem linhas de resultado para ${year}.`}</Empty>
                )}
                {(resultado?.items || []).map((row, i) => (
                  <div key={String(row.id || i)} className="list-item">
                    <span className="item-title">
                      {String(row.reference_period || row.period || "—")}
                    </span>
                    <span className="item-meta">
                      primário:{" "}
                      {formatContasValue(
                        row.primary_result as number | undefined,
                        "BRL_millions"
                      )}{" "}
                      · nominal:{" "}
                      {formatContasValue(
                        row.nominal_result as number | undefined,
                        "BRL_millions"
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {(tab === "resumo" || tab === "divida") && (
            <section className="stack">
              <h2 className="section-title">Dívida (amostra {year})</h2>
              <p className="prose-note">Não misturar DPF, DBGG e DLSP.</p>
              <div className="list-block">
                {(divida?.items || []).length === 0 && (
                  <Empty>{`Sem linhas de dívida para ${year}.`}</Empty>
                )}
                {(divida?.items || []).map((row, i) => (
                  <div key={String(row.id || i)} className="list-item">
                    <span className="item-title">
                      {String(row.debt_indicator || "dívida")} ·{" "}
                      {String(row.reference_period || "—")}
                    </span>
                    <span
                      className="item-meta"
                      title={
                        formatContasExact(
                          row.stock as number | undefined,
                          "BRL"
                        ) || undefined
                      }
                    >
                      estoque:{" "}
                      {formatContasValue(row.stock as number | undefined, "BRL")}
                      {row.debt_type ? ` · ${String(row.debt_type)}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {(tab === "resumo" || tab === "renuncias") && (
            <section className="stack">
              <h2 className="section-title">Renúncias fiscais {year}</h2>
              <p className="prose-note">
                {renuncias?.nota ||
                  "Renúncia ≠ pagamento. Agregado anual federal (RFB)."}
              </p>
              <div className="list-block">
                {(renuncias?.items || []).length === 0 && (
                  <Empty>
                    {renuncias?.error
                      ? `Erro: ${renuncias.error}`
                      : `Sem agregados de renúncia para ${year}.`}
                  </Empty>
                )}
                {(renuncias?.items || []).map((row, i) => (
                  <div
                    key={String(row.tax_expenditure_id || i)}
                    className="list-item"
                  >
                    <span className="item-title">
                      Total federal · {String(row.year || year)}
                    </span>
                    <span
                      className="item-meta"
                      title={
                        formatContasExact(
                          row.valor as number | undefined,
                          "BRL"
                        ) || undefined
                      }
                    >
                      {formatContasValue(row.valor as number | undefined, "BRL")}{" "}
                      · {String(row.value_type || "—")}
                    </span>
                  </div>
                ))}
              </div>
              {tab === "resumo" ? (
                <p className="item-meta muted">
                  <Link href={qs({ year, tab: "renuncias" })}>
                    Ranking · para quem (beneficiários) →
                  </Link>
                </p>
              ) : null}
            </section>
          )}

          {tab === "renuncias" && (
            <section className="stack">
              <h2 className="section-title">
                Ranking — para quem · maiores valores {year}
              </h2>
              <p className="prose-note">
                {beneficiarios?.nota ||
                  "Lista por CNPJ raiz / razão social na fonte RFB. Renúncia ≠ pagamento público."}
              </p>
              <form className="filters atlas-money-filters" method="get">
                <input type="hidden" name="year" value={year} />
                <input type="hidden" name="tab" value="renuncias" />
                <input
                  name="q"
                  defaultValue={searchParams.q || ""}
                  placeholder="Filtrar nome / CNPJ / tributo…"
                />
                <select name="sort" defaultValue={sort}>
                  <option value="desc">Maior valor</option>
                  <option value="asc">Menor valor</option>
                </select>
                <button className="btn" type="submit">
                  Filtrar
                </button>
              </form>
              <div className="list-block">
                {benefRows.length === 0 && (
                  <Empty>
                    {beneficiarios?.error
                      ? `Erro: ${beneficiarios.error}`
                      : q
                        ? "Nenhum beneficiário neste filtro."
                        : `Sem beneficiários materializados para ${year}.`}
                  </Empty>
                )}
                {benefRows.map((row, i) => {
                  const nome = String(
                    row.razao_social || row.cnpj_raiz || "Beneficiário"
                  );
                  const raiz = row.cnpj_raiz ? String(row.cnpj_raiz) : "";
                  const companyId = row.company_id
                    ? String(row.company_id)
                    : null;
                  const hrefEmpresa = companyId
                    ? `/empresas/${companyId}`
                    : `/empresas?q=${encodeURIComponent(nome)}`;
                  const valor = row.valor as number | undefined;
                  return (
                    <div
                      key={String(row.tax_expenditure_id || i)}
                      className="list-item atlas-rank-row"
                    >
                      <span className="atlas-rank-pos">#{i + 1}</span>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span className="item-title">
                          <Link href={hrefEmpresa}>{nome}</Link>
                        </span>
                        <span
                          className="item-meta"
                          title={formatContasExact(valor, "BRL") || undefined}
                        >
                          {formatContasValue(valor, "BRL")}
                          {raiz ? ` · CNPJ raiz ${raiz}` : ""}
                          {row.tributo ? ` · ${String(row.tributo)}` : ""}
                        </span>
                      </span>
                    </div>
                  );
                })}
                {typeof beneficiarios?.total === "number" &&
                  beneficiarios.total > 0 && (
                    <p className="item-meta muted">
                      Ranking top por valor · mostrando {benefRows.length}
                      {q ? " (filtrado)" : ""} de até{" "}
                      {beneficiarios.items?.length || 0} carregados (
                      {beneficiarios.total} no serving).
                    </p>
                  )}
              </div>
            </section>
          )}

          {(tab === "resumo" || tab === "pessoal") && (
            <section className="stack">
              <h2 className="section-title">Pessoal (SICONFI) {year}</h2>
              <div className="list-block">
                {(pessoal?.items || []).length === 0 && (
                  <Empty>{`Sem despesas de pessoal para ${year}.`}</Empty>
                )}
                {(pessoal?.items || []).map((row, i) => (
                  <div key={String(row.id || i)} className="list-item">
                    <span className="item-title">
                      {String(row.territory_id || "—")} ·{" "}
                      {String(row.government_level || "")} ·{" "}
                      {String(row.reference_period || "")}
                    </span>
                    <span
                      className="item-meta"
                      title={
                        formatContasExact(
                          row.gross_amount as number | undefined,
                          (row.currency as string) || "BRL"
                        ) || undefined
                      }
                    >
                      bruto:{" "}
                      {formatContasValue(
                        row.gross_amount as number | undefined,
                        (row.currency as string) || "BRL"
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {tab === "cno" && (
            <section className="stack">
              <h2 className="section-title">Cadastro Nacional de Obras (CNO)</h2>
              <p className="prose-note">
                {cno?.nota ||
                  "Obra cadastrada na RFB. company_id só com CNPJ 14. Não implica irregularidade."}
              </p>
              <form className="filters atlas-money-filters" method="get">
                <input type="hidden" name="year" value={year} />
                <input type="hidden" name="tab" value="cno" />
                <input
                  name="uf"
                  defaultValue={uf}
                  placeholder="UF"
                  maxLength={2}
                  style={{ width: 64, textTransform: "uppercase" }}
                />
                <button className="btn" type="submit">
                  Filtrar UF
                </button>
              </form>
              <div className="list-block">
                {(cno?.items || []).length === 0 && (
                  <Empty>
                    {cno?.error
                      ? `Erro: ${cno.error}`
                      : "Sem obras CNO no serving (rode o loader Contas)."}
                  </Empty>
                )}
                {(cno?.items || []).map((row, i) => (
                  <div key={String(row.cno_work_id || i)} className="list-item">
                    <span className="item-title">
                      CNO {String(row.cno_id || "—")} · {String(row.uf || "—")}
                      {row.municipality ? ` / ${String(row.municipality)}` : ""}
                    </span>
                    <span className="item-meta">
                      CNPJ: {String(row.cnpj || "—")}
                      {row.company_id ? ` · ${String(row.company_id)}` : ""}
                    </span>
                  </div>
                ))}
                {typeof cno?.total === "number" && cno.total > 0 && (
                  <p className="item-meta muted">
                    Mostrando {(cno.items || []).length} de {cno.total} obras no
                    serving{uf ? ` · UF ${uf}` : ""}.
                  </p>
                )}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
