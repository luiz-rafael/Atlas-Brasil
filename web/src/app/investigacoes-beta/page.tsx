import Link from "next/link";
import InvestigacoesBetaGraph from "@/components/InvestigacoesBetaGraph";
import {
  ACTION_LABEL,
  NUCLEUS_LABEL,
  STATUS_LABEL,
  STATUS_TONE,
  buildInvestigacoesBetaGraph,
  companyOrCourtName,
  eventsForCase,
  latestStatusByPerson,
  loadInvestigacoesBeta,
  loadInvestigacoesBetaFotos,
  participationsForCase,
  personName,
} from "@/lib/investigacoes-beta";

export const dynamic = "force-dynamic";

const REL_LABEL: Record<string, string> = {
  mentioned_in_context: "Citado no contexto",
  contrato_contexto: "Contratos no contexto",
  orgao_contexto: "Órgão / juízo no contexto",
};

const TYPE_LABEL: Record<string, string> = {
  company: "Empresa",
  government_org: "Órgão público",
  legislature: "Casa legislativa",
  court: "Vara / tribunal",
  court_body: "Colegiado",
};

export default function InvestigacoesBetaPage({
  searchParams,
}: {
  searchParams?: { caso?: string; pessoa?: string };
}) {
  const data = loadInvestigacoesBeta();
  if (!data.cases.length) {
    return (
      <div className="page stack">
        <h1>Investigações</h1>
        <p className="muted">
          Mock de demonstração indisponível neste ambiente. O restante do Atlas
          (pessoas, indicadores) usa a API.
        </p>
      </div>
    );
  }
  const caseId = searchParams?.caso || "stf_inq_4325";
  const selected = data.cases.find((c) => c.id === caseId) || data.cases[0];
  const parts = participationsForCase(data, selected.id);
  const peopleRows = latestStatusByPerson(parts, data);
  const events = eventsForCase(data, selected.id);
  const children = data.cases.filter((c) => c.parent_id === "stf_inq_3989");
  const focusPerson = searchParams?.pessoa;
  const graph = buildInvestigacoesBetaGraph(data, {
    mode: "full",
    photos: loadInvestigacoesBetaFotos(),
  });
  const companies = data.companies || [];
  const courts = data.courts || [];
  const sources = data.sources || [];
  const decisions = [...(data.decisions || [])].sort((a, b) =>
    String(a.at).localeCompare(String(b.at))
  );
  const caseLinks = (data.case_company_links || []).filter(
    (l) => l.case_id === selected.id
  );

  return (
    <div className="page stack inv-beta-page">
      <header className="inv-beta-hero">
        <p className="eyebrow">Lava Jato · cluster INQ 3989 · STF</p>
        <h1 className="section-title">Investigações</h1>
        <p className="muted">
          Inquéritos do STF ligados ao INQ 3989 e aos desdobramentos 4325, 4326,
          4327 e 4631. Processo não é culpa.
        </p>
      </header>

      <section className="panel stack">
        <h2>Estrutura</h2>
        <p className="muted">
          Em 2016, Teori Zavascki desmembrou o INQ 3989: 4325 (PT), 4326 (PMDB
          Senado), 4327 (PMDB Câmara); o PP ficou no 3989. Depois veio o 4631
          (Queiroz Galvão).
        </p>
        <div className="inv-tree">
          <div className="inv-tree-root">{data.operation.name}</div>
          <div className="inv-tree-branch">
            <Link
              href="/investigacoes-beta?caso=stf_inq_3989"
              className={
                selected.id === "stf_inq_3989" ? "inv-node active" : "inv-node"
              }
            >
              INQ 3989 — Progressistas (PP)
            </Link>
            <div className="inv-tree-children">
              {children.map((c) => (
                <Link
                  key={c.id}
                  href={`/investigacoes-beta?caso=${c.id}`}
                  className={
                    selected.id === c.id ? "inv-node active" : "inv-node"
                  }
                >
                  <strong>{c.number}</strong>
                  <span>{NUCLEUS_LABEL[c.nucleus] || c.nucleus}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="panel stack" id="grafo">
        <h2>Grafo</h2>
        <InvestigacoesBetaGraph
          nodes={graph.nodes}
          edges={graph.edges}
          centro={selected.id}
          caseLabel={selected.number}
        />
      </section>

      <section className="panel stack">
        <h2>{selected.number}</h2>
        <p className="muted">{selected.title}</p>

        <h3>Eventos</h3>
        <div className="list-block">
          {events.length ? (
            events.map((ev) => (
              <div
                key={ev.id}
                className={`list-item${ev.highlight ? " inv-event-hi" : ""}`}
              >
                <span className="item-title">
                  {ev.at}
                  {ev.body ? ` · ${ev.body}` : ""}
                </span>
                <span className="item-meta">{ev.summary}</span>
                {ev.source_url ? (
                  <a
                    href={ev.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="faint"
                  >
                    Fonte STF
                  </a>
                ) : null}
              </div>
            ))
          ) : (
            <p className="muted">Sem eventos neste inquérito.</p>
          )}
        </div>

        {caseLinks.length ? (
          <>
            <h3>Empresas e órgãos no contexto</h3>
            <div className="list-block">
              {caseLinks.map((l) => (
                <div
                  key={`${l.case_id}_${l.company_id}_${l.relation}`}
                  className="list-item"
                >
                  <span className="item-title">
                    {companyOrCourtName(data, l.company_id)}
                  </span>
                  <span className="item-meta">
                    {REL_LABEL[l.relation] || l.relation}
                    {l.note ? ` — ${l.note}` : ""}
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : null}

        <h3>Pessoas</h3>
        <div className="list-block">
          {peopleRows.map(({ person_id, latest, history }) => {
            const name = personName(data, person_id);
            const atlas = data.people.find((p) => p.id === person_id)?.atlas_id;
            const open = focusPerson === person_id;
            return (
              <div key={person_id} className="inv-person-row">
                <div className="inv-person-head">
                  <div>
                    {atlas ? (
                      <Link href={`/pessoas/${atlas}`} className="item-title">
                        {name}
                      </Link>
                    ) : (
                      <span className="item-title">{name}</span>
                    )}
                    <span className="item-meta">
                      {history.length}{" "}
                      {history.length === 1 ? "registro" : "registros"}
                    </span>
                  </div>
                  <span className={`badge ${STATUS_TONE[latest.status] || ""}`}>
                    {STATUS_LABEL[latest.status] || latest.status}
                  </span>
                </div>
                <details open={open}>
                  <summary>Linha do tempo</summary>
                  <ul className="inv-timeline">
                    {[...history]
                      .sort((a, b) =>
                        String(a.valid_from || "").localeCompare(
                          String(b.valid_from || "")
                        )
                      )
                      .map((h) => (
                        <li key={h.id}>
                          <strong>{h.valid_from || "—"}</strong>{" "}
                          {STATUS_LABEL[h.status] || h.status}
                          {h.note ? (
                            <span className="muted"> — {h.note}</span>
                          ) : null}
                        </li>
                      ))}
                  </ul>
                </details>
              </div>
            );
          })}
        </div>
      </section>

      <section className="panel stack">
        <h2>Empresas e órgãos</h2>
        <div className="inv-inst-grid">
          {companies.map((co) => (
            <div key={co.id} className="inv-inst-card">
              <p className="item-title">{co.name}</p>
              <p className="item-meta">{TYPE_LABEL[co.type] || co.type}</p>
              {co.note ? <p className="muted">{co.note}</p> : null}
            </div>
          ))}
        </div>
        <h3>Varas e colegiados</h3>
        <div className="list-block">
          {courts.map((ct) => (
            <div key={ct.id} className="list-item">
              <span className="item-title">{ct.name}</span>
              <span className="item-meta">
                {TYPE_LABEL[ct.type] || ct.type}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel stack">
        <h2>Decisões</h2>
        <div className="inv-inst-grid">
          {data.institutions_roles.map((r) => {
            const org = data.organizations.find((o) => o.id === r.actor_id);
            return (
              <div key={`${r.actor_id}_${r.role}`} className="inv-inst-card">
                <p className="item-title">{org?.name || r.actor_id}</p>
                <p className="item-meta">{r.role}</p>
                <p className="muted">{r.note}</p>
              </div>
            );
          })}
        </div>
        <div className="list-block">
          {decisions.map((d, i) => {
            const src = sources.find((s) => s.id === d.source_id);
            return (
              <div
                key={`${d.at}_${d.actor_id}_${d.action}_${i}`}
                className="list-item"
              >
                <span className="item-title">
                  {d.at} ·{" "}
                  {data.people.some((p) => p.id === d.actor_id)
                    ? personName(data, d.actor_id)
                    : companyOrCourtName(data, d.actor_id)}
                </span>
                <span className="item-meta">
                  {d.body} · {ACTION_LABEL[d.action] || d.action} ·{" "}
                  {data.cases.find((c) => c.id === d.case_id)?.number ||
                    d.case_id}
                </span>
                <span className="muted">{d.summary}</span>
                {src?.url ? (
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="faint"
                  >
                    {src.title.length > 80
                      ? `${src.title.slice(0, 80)}…`
                      : src.title}
                  </a>
                ) : null}
              </div>
            );
          })}
        </div>
        <h3>Relatores</h3>
        <div className="list-block">
          {data.reporters.map((r) => (
            <div key={`${r.person_id}_${r.valid_from}`} className="list-item">
              <span className="item-title">
                {personName(data, r.person_id)}
              </span>
              <span className="item-meta">
                {r.valid_from || "…"} → {r.valid_to || "em curso"} ·{" "}
                {r.case_ids.length} inquéritos
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel stack">
        <h2>Fontes</h2>
        <div className="list-block">
          {sources.map((s) => (
            <div key={s.id} className="list-item">
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="item-title"
              >
                {s.title}
              </a>
              <span className="item-meta">
                {s.publisher || "STF"}
                {s.at ? ` · ${s.at}` : ""}
                {s.case_ids?.length
                  ? ` · ${s.case_ids
                      .map(
                        (id) =>
                          data.cases.find((c) => c.id === id)?.number || id
                      )
                      .join(", ")}`
                  : ""}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel stack">
        <h2>Carreira política e história jurídica</h2>
        <div className="inv-rails">
          {data.dual_rails.map((rail) => {
            const atlas = data.people.find(
              (p) => p.id === rail.person_id
            )?.atlas_id;
            return (
              <article key={rail.person_id} className="inv-rail">
                <h3>
                  {atlas ? (
                    <Link href={`/pessoas/${atlas}`}>{rail.name}</Link>
                  ) : (
                    rail.name
                  )}
                </h3>
                <div className="inv-rail-cols">
                  <div>
                    <h4>Político</h4>
                    <ul>
                      {rail.political.map((x) => (
                        <li key={x.label}>
                          <strong>{x.at}</strong> — {x.label}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4>Jurídico</h4>
                    <ul>
                      {rail.legal.map((x) => (
                        <li key={x.label}>
                          <strong>{x.at}</strong> — {x.label}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <p className="faint" style={{ marginTop: "0.5rem" }}>
        <Link href="/casos">Justiça</Link>
        {" · "}
        <Link href="/pessoas/p_cam_107283">Gleisi Hoffmann</Link>
        {" · "}
        <Link href="/pessoas/p_cam_160541">Arthur Lira</Link>
      </p>
    </div>
  );
}
