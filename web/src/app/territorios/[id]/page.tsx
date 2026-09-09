import Link from "next/link";
import { notFound } from "next/navigation";
import { BR_STATE_PATHS } from "@/lib/br-states-paths";
import {
  BR_UF_CAPITAL,
  BR_UF_REGION,
} from "@/lib/br-uf-meta";
import {
  fetchAdministrations,
  fetchTerritoryContext,
  fetchTerritoryTimeline,
} from "@/lib/administrations";
import AtlasTemporalSlider from "@/components/AtlasTemporalSlider";
import { formatIndicatorValue, listYears } from "@/lib/indicators";
import {
  ATLAS_CATEGORIES,
  indicatorDef,
} from "@/lib/indicator-taxonomy";

const TABS = [
  { id: "resumo", label: "Resumo" },
  { id: "indicadores", label: "Indicadores" },
  { id: "governos", label: "Governos" },
  { id: "economia", label: "Economia" },
  { id: "seguranca", label: "Segurança" },
  { id: "saude", label: "Saúde" },
  { id: "educacao", label: "Educação" },
  { id: "saneamento", label: "Saneamento" },
  { id: "contas", label: "Contas" },
  { id: "contratos", label: "Contratos" },
  { id: "historia", label: "História" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const HERO_INDS = [
  "ind_pop_estimada",
  "ind_pib_corrente",
  "ind_pib_per_capita",
] as const;

const DOMAIN_INDS: Record<string, string[]> = {
  economia: ["ind_pib_corrente", "ind_pib_per_capita", "ind_pop_estimada"],
  seguranca: ["ind_homicidios_per_100k", "ind_homicidios", "ind_cvli_per_100k"],
  saude: [
    "ind_mortalidade_infantil",
    "ind_mortalidade_geral",
    "ind_natalidade",
  ],
  educacao: [
    "ind_ideb_anos_iniciais",
    "ind_ideb_anos_finais",
    "ind_ideb_ensino_medio",
  ],
  saneamento: [],
};

function labelFor(indId: string): string {
  return indicatorDef(indId)?.label || indId.replace(/^ind_/, "").replace(/_/g, " ");
}

function yearOf(date?: string | null): string {
  if (!date) return "?";
  return date.slice(0, 4);
}

export default async function TerritorioPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { ano?: string; ind?: string; tab?: string };
}) {
  let tid = params.id;
  let uf: string | null = null;
  if (tid.length === 2 && /^[a-zA-Z]{2}$/.test(tid)) {
    uf = tid.toUpperCase();
    tid = `uf_${uf}`;
  } else if (tid.startsWith("uf_")) {
    uf = tid.slice(3).toUpperCase();
  }

  const nome =
    (uf && BR_STATE_PATHS.find((s) => s.uf === uf)?.nome) || tid;
  if (uf && !BR_STATE_PATHS.some((s) => s.uf === uf)) notFound();

  const tab = (TABS.some((t) => t.id === searchParams?.tab)
    ? searchParams?.tab
    : "resumo") as TabId;

  const domainInds =
    tab in DOMAIN_INDS ? DOMAIN_INDS[tab] : ([] as string[]);
  const requestInds = [
    ...HERO_INDS,
    ...(domainInds.length ? domainInds : []),
    "ind_homicidios_per_100k",
    "ind_mortalidade_infantil",
    "ind_ideb_anos_finais",
  ];
  const uniqueInds = [...new Set(requestInds)];

  const popYears = await listYears("ind_pop_estimada");
  const years = popYears.length
    ? popYears
    : await listYears("ind_pib_corrente");
  const latest = years[years.length - 1] || 2023;
  const ano = Math.min(
    latest,
    Math.max(years[0] || 2002, Number(searchParams?.ano || latest) || latest)
  );

  const [ctx, admins, timeline] = await Promise.all([
    fetchTerritoryContext(tid, ano, uniqueInds),
    uf
      ? fetchAdministrations({ state_code: uf, limit: 80 })
      : fetchAdministrations({ territory_id: tid, limit: 80 }),
    fetchTerritoryTimeline(tid, 40),
  ]);

  const byId = Object.fromEntries(
    (ctx?.indicators || []).map((o) => [
      String(o.indicator_id),
      Number(o.value),
    ])
  );

  const terr = (ctx?.territory || {}) as Record<string, unknown>;
  const region =
    String(terr.region_name || (uf && BR_UF_REGION[uf]) || "—");
  const capital = (uf && BR_UF_CAPITAL[uf]) || "—";
  const adm = ctx?.administration;

  const tabHref = (t: TabId) =>
    `/territorios/${params.id}?ano=${ano}&tab=${t}`;

  const indRows = (ids: string[]) =>
    ids
      .map((id) => ({
        id,
        label: labelFor(id),
        value: byId[id],
      }))
      .filter((r) => r.value != null && Number.isFinite(r.value));

  const resumoCards = [
    ...indRows([...HERO_INDS]),
    ...indRows([
      "ind_ideb_anos_finais",
      "ind_mortalidade_infantil",
      "ind_homicidios_per_100k",
    ]),
  ];

  // Timeline agrupada por década (§23)
  const byDecade = new Map<string, typeof timeline>();
  for (const ev of timeline) {
    const y = yearOf(ev.start_date);
    const decade = y === "?" ? "—" : `${Math.floor(Number(y) / 10) * 10}s`;
    if (!byDecade.has(decade)) byDecade.set(decade, []);
    byDecade.get(decade)!.push(ev);
  }

  return (
    <div className="page atlas-territory">
      <header className="atlas-territory-hero">
        <p className="eyebrow">
          Território · {region}
          {uf ? ` · ${uf}` : ""}
        </p>
        <h1 className="atlas-territory-title">{nome}</h1>
        <p className="atlas-territory-lede">
          Como estava a vida e a economia neste território em {ano} — e quem
          governava. Indicadores são observações; não são nota do governo.
        </p>

        <dl className="atlas-territory-stats">
          <div>
            <dt>População</dt>
            <dd>
              {byId.ind_pop_estimada != null
                ? formatIndicatorValue(
                    "ind_pop_estimada",
                    byId.ind_pop_estimada
                  )
                : "—"}
            </dd>
          </div>
          <div>
            <dt>PIB</dt>
            <dd>
              {byId.ind_pib_corrente != null
                ? formatIndicatorValue(
                    "ind_pib_corrente",
                    byId.ind_pib_corrente
                  )
                : "—"}
            </dd>
          </div>
          <div>
            <dt>PIB per capita</dt>
            <dd>
              {byId.ind_pib_per_capita != null
                ? formatIndicatorValue(
                    "ind_pib_per_capita",
                    byId.ind_pib_per_capita
                  )
                : "—"}
            </dd>
          </div>
          <div>
            <dt>Capital</dt>
            <dd>{capital}</dd>
          </div>
          <div>
            <dt>Região</dt>
            <dd>{region}</dd>
          </div>
        </dl>
      </header>

      <AtlasTemporalSlider
        years={years.filter((y) => y >= 2000 || y === years[0])}
        year={ano}
        basePath={`/territorios/${params.id}`}
        preserve={{ tab }}
      />

      <div className="atlas-gov-levels" aria-label="Níveis de governo">
        <div className="atlas-gov-level">
          <span className="atlas-gov-level-k">Estado</span>
          <strong>
            {adm?.executive_person_name || "Sem titular documentado"}
          </strong>
          <em>
            {[
              adm?.party_at_start,
              adm?.start_date
                ? `${yearOf(adm.start_date)}–${yearOf(adm.end_date)}`
                : null,
            ]
              .filter(Boolean)
              .join(" · ") || `Em ${ano}`}
          </em>
          {adm?.executive_person_id ? (
            <Link href={`/pessoas/${adm.executive_person_id}`}>Ver perfil</Link>
          ) : null}
        </div>
        <div className="atlas-gov-level muted">
          <span className="atlas-gov-level-k">Brasil</span>
          <strong>Presidência</strong>
          <em>Cobertura federal em expansão no Atlas</em>
        </div>
      </div>

      <nav className="atlas-territory-tabs" aria-label="Seções do território">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={tabHref(t.id)}
            className={tab === t.id ? "active" : undefined}
          >
            {t.label}
          </Link>
        ))}
      </nav>

      {tab === "resumo" && (
        <section className="atlas-territory-section stack">
          <h2 className="section-title">Resumo · {ano}</h2>
          <p className="prose-note">
            {ctx?.note ||
              "Indicadores observados no ano — não atribuem efeito ao titular."}
          </p>
          <div className="atlas-territory-metric-grid">
            {resumoCards.map((c) => (
              <div key={c.id} className="atlas-territory-metric">
                <span>{c.label}</span>
                <strong>
                  {formatIndicatorValue(c.id, c.value as number)}
                </strong>
              </div>
            ))}
            {!resumoCards.length ? (
              <p className="muted">Sem indicadores para este ano.</p>
            ) : null}
          </div>
          <div className="chips">
            <Link
              className="chip"
              href={`/indicadores?ano=${ano}&sel=${uf || ""}`}
            >
              Abrir no mapa
            </Link>
            <Link className="chip" href={`/contas?year=${ano}&tab=resumo`}>
              Contas do Brasil
            </Link>
            {uf ? (
              <Link
                className="chip"
                href={`/indicadores/uf/${uf}?ano=${ano}`}
              >
                Série do estado
              </Link>
            ) : null}
          </div>
        </section>
      )}

      {tab === "indicadores" && (
        <section className="atlas-territory-section stack">
          <h2 className="section-title">Indicadores · {ano}</h2>
          <div className="list-block">
            {(ctx?.indicators || []).map((o) => {
              const id = String(o.indicator_id);
              return (
                <div key={String(o.observation_id || id)} className="list-item">
                  <p className="item-title">{labelFor(id)}</p>
                  <p className="item-meta">
                    {formatIndicatorValue(id, Number(o.value || 0))}
                    {" · "}
                    <Link
                      href={`/indicadores?ind=${id}&ano=${ano}&sel=${uf || ""}`}
                    >
                      no mapa
                    </Link>
                  </p>
                </div>
              );
            })}
            {!ctx?.indicators?.length ? (
              <p className="muted">Sem observações neste ano.</p>
            ) : null}
          </div>
        </section>
      )}

      {tab === "governos" && (
        <section className="atlas-territory-section stack">
          <h2 className="section-title">Governos documentados</h2>
          <p className="prose-note">
            Mandatos estaduais com fonte. Troca de titular não implica julgamento
            de desempenho.
          </p>
          <div className="list-block">
            {admins.map((a) => (
              <div key={a.administration_id} className="list-item">
                <p className="item-title">
                  {a.executive_person_name || a.administration_id}
                </p>
                <p className="item-meta">
                  {a.start_date} → {a.end_date || "…"}
                  {a.party_at_start ? ` · ${a.party_at_start}` : ""}
                  {a.executive_person_id ? (
                    <>
                      {" · "}
                      <Link href={`/pessoas/${a.executive_person_id}`}>
                        perfil
                      </Link>
                    </>
                  ) : null}
                </p>
              </div>
            ))}
            {!admins.length ? (
              <p className="muted">Sem administrações neste território.</p>
            ) : null}
          </div>
        </section>
      )}

      {["economia", "seguranca", "saude", "educacao", "saneamento"].includes(
        tab
      ) && (
        <section className="atlas-territory-section stack">
          <h2 className="section-title">
            {TABS.find((t) => t.id === tab)?.label} · {ano}
          </h2>
          {tab === "saneamento" && !DOMAIN_INDS.saneamento.length ? (
            <p className="muted">
              Série de saneamento ainda não materializada no serving deste
              território. Acompanhe a categoria em{" "}
              <Link href="/indicadores?cat=saneamento">Indicadores</Link>.
            </p>
          ) : (
            <div className="atlas-territory-metric-grid">
              {indRows(DOMAIN_INDS[tab] || []).map((c) => (
                <div key={c.id} className="atlas-territory-metric">
                  <span>{c.label}</span>
                  <strong>
                    {formatIndicatorValue(c.id, c.value as number)}
                  </strong>
                  <Link
                    href={`/indicadores?cat=${tab}&ind=${c.id}&ano=${ano}&sel=${uf || ""}`}
                  >
                    Ver no mapa
                  </Link>
                </div>
              ))}
              {!indRows(DOMAIN_INDS[tab] || []).length ? (
                <p className="muted">Sem dado para estes indicadores em {ano}.</p>
              ) : null}
            </div>
          )}
          {ATLAS_CATEGORIES.find((c) => c.id === tab)?.note ? (
            <p className="prose-note">
              {ATLAS_CATEGORIES.find((c) => c.id === tab)?.note}
            </p>
          ) : null}
        </section>
      )}

      {tab === "contas" && (
        <section className="atlas-territory-section stack">
          <h2 className="section-title">Contas públicas</h2>
          <p className="muted">
            Resultado fiscal, dívida e renúncias estão no módulo Contas (visão
            canônica Brasil). Recorte estadual de SICONFI entra pelas séries de
            receita/despesa nos indicadores.
          </p>
          <div className="chips">
            <Link className="chip" href={`/contas?year=${ano}&tab=resumo`}>
              Abrir Contas · {ano}
            </Link>
            <Link
              className="chip"
              href={`/indicadores?cat=contas&ano=${ano}&sel=${uf || ""}`}
            >
              Receitas e despesas no mapa
            </Link>
            <Link className="chip" href={`/contas?year=${ano}&tab=renuncias`}>
              Renúncias (beneficiários)
            </Link>
          </div>
        </section>
      )}

      {tab === "contratos" && (
        <section className="atlas-territory-section stack">
          <h2 className="section-title">Contratos e fluxos</h2>
          <p className="muted">
            Contratos PNCP, emendas e despesas parlamentares ficam em Dinheiro
            público — evidência documental, sem acusação.
          </p>
          <div className="chips">
            <Link className="chip" href="/dinheiro">
              Abrir Dinheiro
            </Link>
            <Link className="chip" href={`/contas?year=${ano}&tab=cno`}>
              Obras (CNO)
            </Link>
          </div>
        </section>
      )}

      {tab === "historia" && (
        <section className="atlas-territory-section stack">
          <h2 className="section-title">História administrativa</h2>
          <p className="prose-note">
            Timeline agrupada por década — só eventos de governo documentados.
            Não é narrativa completa do estado.
          </p>
          <div className="atlas-territory-timeline">
            {[...byDecade.entries()]
              .sort((a, b) => b[0].localeCompare(a[0]))
              .map(([decade, events]) => (
              <div key={decade} className="atlas-territory-decade">
                <h3>{decade}</h3>
                <ul>
                  {events.map((ev) => (
                    <li key={String(ev.event_id || ev.label)}>
                      <strong>
                        {yearOf(ev.start_date)}–{yearOf(ev.end_date)}
                      </strong>
                      <span>
                        {ev.person_id ? (
                          <Link href={`/pessoas/${ev.person_id}`}>
                            {ev.label}
                          </Link>
                        ) : (
                          ev.label
                        )}
                        {ev.party ? ` · ${ev.party}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {!timeline.length ? (
              <p className="muted">Sem eventos de administração na timeline.</p>
            ) : null}
          </div>
        </section>
      )}
    </div>
  );
}
