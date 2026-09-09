"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import type { Entidade, Relacao, Registro, Caso } from "@/lib/kb-types";
import { formatBRL, STATUS_LABEL } from "@/lib/format";
import { camaraProposicaoUrl, propLabel } from "@/lib/camara-links";
import ProfileNarrative from "./ProfileNarrative";
import ProfileShortcutCards from "./ProfileShortcutCards";
import ProfileMicroGraph from "./ProfileMicroGraph";
import type { ProfileTabId } from "./tabs";
import type { GEdge, GNode } from "@/components/InteractiveGraph";

function Empty({ children }: { children: ReactNode }) {
  return <p className="muted profile-empty">{children}</p>;
}

function hrefOther(id: string) {
  if (id.startsWith("c_")) return `/casos/${id}`;
  if (id.startsWith("pt_")) return `/partidos/${id}`;
  if (id.startsWith("p_")) return `/pessoas/${id}`;
  if (id.startsWith("inst_")) return `/instituicoes/${id}`;
  if (id.startsWith("e_") || id.startsWith("emp_")) return `/empresas/${id}`;
  return `/grafo?centro=${id}`;
}

export default function ProfilePanels({
  tab,
  pessoa,
  rels,
  regs,
  casos,
  labels,
  fontes,
  graphNodes,
  graphEdges,
  onTab,
}: {
  tab: ProfileTabId;
  pessoa: Entidade;
  rels: Relacao[];
  regs: Registro[];
  casos: Record<string, Pick<Caso, "id" | "nome">>;
  labels: Record<string, string>;
  fontes: string[];
  graphNodes: GNode[];
  graphEdges: Array<
    GEdge & { justificativa_documental?: string; contexto?: string; periodo?: string }
  >;
  onTab?: (tab: ProfileTabId) => void;
}) {
  const nameOf = (id: string) => labels[id] || id;
  const [projVisible, setProjVisible] = useState(30);
  const autorProps = rels.filter((r) => r.tipo === "autor_de_proposicao");
  const mentioned = rels.filter((r) => r.tipo === "mentioned_in");
  const empresaRels = rels.filter(
    (r) =>
      r.tipo.includes("socio") ||
      r.tipo.includes("empresa") ||
      r.tipo.includes("contrato") ||
      r.tipo.includes("fornecedor") ||
      r.tipo.includes("despesa_parlamentar") ||
      r.tipo.includes("despesa_campanha") ||
      r.tipo === "pagou_despesa_parlamentar_a" ||
      r.tipo === "pagou_despesa_campanha_a" ||
      r.tipo === "emenda_beneficiou" ||
      r.tipo === "fornecido_por" ||
      r.tipo === "dono_de" ||
      r.tipo === "socio_de"
  );
  const frentes = rels.filter((r) => r.tipo === "membro_de");
  const bensRels = rels.filter((r) => r.tipo === "declarou_bem");
  const leg = pessoa.legislativo_resumo;

  if (tab === "resumo") {
    return (
      <div className="stack">
        <ProfileShortcutCards
          pessoa={pessoa}
          qtdRelacoes={rels.length}
          qtdCasos={regs.length}
          qtdEmpresas={empresaRels.length}
          qtdDocs={fontes.length}
          onTab={onTab}
        />
        <ProfileNarrative
          pessoa={pessoa}
          qtdRelacoes={rels.length}
          qtdCasos={regs.length}
        />
        <div className="dash-split" style={{ gridTemplateColumns: "1.2fr 0.8fr" }}>
          <section className="panel stack">
            <h2>Resumo factual</h2>
            <p className="muted">
              {pessoa.no_poder_2026
                ? "Mandato/exercício listado em dados abertos da Casa Legislativa ou executivo."
                : "Registro público sem mandato federal atual neste corte."}
              {pessoa.tags?.includes("coletado")
                ? " Dados provenientes de coleta oficial."
                : ""}
            </p>
            {pessoa.gabinete && (pessoa.gabinete.telefone || pessoa.gabinete.sala) ? (
              <>
                <h3>Gabinete</h3>
                <p className="muted">
                  {[pessoa.gabinete.nome, pessoa.gabinete.predio, pessoa.gabinete.sala]
                    .filter(Boolean)
                    .join(" · ")}
                  {pessoa.gabinete.telefone
                    ? ` · Tel. ${pessoa.gabinete.telefone}`
                    : ""}
                </p>
              </>
            ) : null}
            {(pessoa.mandatos || []).length > 0 ? (
              <>
                <h3>Mandatos</h3>
                <div className="list-block">
                  {(pessoa.mandatos || []).map((m) => (
                    <div key={m.id || m.cargo + String(m.ano_eleicao)} className="list-item">
                      <p className="item-title">
                        {m.cargo || "Mandato"}
                        {m.uf ? " · " + m.uf : ""}
                      </p>
                      <p className="item-meta">
                        {m.ano_eleicao != null ? "Eleição " + m.ano_eleicao : ""}
                        {m.partido ? " · " + m.partido : ""}
                        {m.inicio || m.fim
                          ? " · " + (m.inicio || "?") + " → " + (m.fim || "?")
                          : ""}
                      </p>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </section>
          <aside className="panel stack">
            <h2>Fontes oficiais</h2>
            <ul className="plain-list">
              {fontes.length === 0 ? (
                <li className="muted">Sem URL de fonte neste registro.</li>
              ) : (
                fontes.slice(0, 8).map((f) => (
                  <li key={f}>
                    <a href={f} target="_blank" rel="noreferrer" className="muted">
                      {f.replace(/^https?:\/\//, "").slice(0, 64)}
                    </a>
                  </li>
                ))
              )}
            </ul>
          </aside>
        </div>
      </div>
    );
  }

  if (tab === "trajetoria") {
    type Mile = { year: string; title: string; meta?: string };
    const miles: Mile[] = [];
    if (pessoa.data_nascimento) {
      miles.push({
        year: String(pessoa.data_nascimento).slice(0, 4),
        title: "Nascimento",
        meta: [
          pessoa.municipio_nascimento,
          pessoa.uf_nascimento,
        ]
          .filter(Boolean)
          .join("/") || undefined,
      });
    }
    if (pessoa.escolaridade) {
      miles.push({
        year: "—",
        title: "Escolaridade",
        meta: pessoa.escolaridade,
      });
    }
    for (const m of [...(pessoa.mandatos || [])].sort((a, b) =>
      String(a.inicio || a.ano_eleicao || "").localeCompare(
        String(b.inicio || b.ano_eleicao || "")
      )
    )) {
      const y = String(m.ano_eleicao || m.inicio || "").slice(0, 4) || "—";
      miles.push({
        year: y,
        title: [m.cargo || "Mandato", m.uf].filter(Boolean).join(" · "),
        meta: [m.partido, m.inicio && m.fim ? `${m.inicio} → ${m.fim}` : null]
          .filter(Boolean)
          .join(" · "),
      });
    }
    if (pessoa.cargo_atual && !(pessoa.mandatos || []).length) {
      miles.push({
        year: "hoje",
        title: pessoa.cargo_atual,
        meta: [pessoa.partido, pessoa.uf].filter(Boolean).join(" · "),
      });
    }
    for (const r of frentes.slice(0, 8)) {
      const other = r.origem === pessoa.id ? r.destino : r.origem;
      miles.push({
        year: (r.periodo || "").slice(0, 4) || "—",
        title: `Membro · ${nameOf(other)}`,
        meta: r.contexto || undefined,
      });
    }

    return (
      <section className="panel stack">
        <h2>Trajetória</h2>
        <p className="muted">
          Marcos derivados dos campos e relações disponíveis — sem biografia
          inventada. Evitamos tabela como visual primário.
        </p>
        <ol className="atlas-profile-timeline">
          {miles.map((m, i) => (
            <li key={`${m.year}-${m.title}-${i}`}>
              <span className="atlas-profile-timeline-year">{m.year}</span>
              <div>
                <strong>{m.title}</strong>
                {m.meta ? <em>{m.meta}</em> : null}
              </div>
            </li>
          ))}
        </ol>
        {!miles.length ? (
          <Empty>Sem eventos de trajetória nesta amostra.</Empty>
        ) : null}
      </section>
    );
  }

  if (tab === "partidos") {
    const parties = new Map<string, string[]>();
    const add = (party?: string | null, note?: string) => {
      if (!party) return;
      const key = party.trim();
      if (!key) return;
      if (!parties.has(key)) parties.set(key, []);
      if (note) parties.get(key)!.push(note);
    };
    add(pessoa.partido, "Partido atual (corte)");
    for (const m of pessoa.mandatos || []) {
      add(
        m.partido,
        [m.cargo, m.uf, m.ano_eleicao != null ? `eleição ${m.ano_eleicao}` : null]
          .filter(Boolean)
          .join(" · ")
      );
    }
    const partidoRels = rels.filter(
      (r) =>
        r.tipo.includes("partido") ||
        r.destino.startsWith("pt_") ||
        r.origem.startsWith("pt_")
    );
    return (
      <section className="panel stack">
        <h2>Partidos</h2>
        <p className="prose-note">
          Filiação e legendas aparecem como documentadas nas fontes — troca de
          partido não implica juízo.
        </p>
        <div className="list-block">
          {Array.from(parties.entries()).map(([party, notes]) => (
            <div key={party} className="list-item">
              <p className="item-title">{party}</p>
              <p className="item-meta">
                {Array.from(new Set(notes)).join(" · ") || "—"}
              </p>
            </div>
          ))}
          {partidoRels.map((r) => {
            const other = r.origem === pessoa.id ? r.destino : r.origem;
            return (
              <div key={r.id} className="list-item">
                <p className="item-title">
                  <Link href={hrefOther(other)}>{nameOf(other)}</Link>
                </p>
                <p className="item-meta">
                  {r.tipo}
                  {r.periodo ? ` · ${r.periodo}` : ""}
                </p>
              </div>
            );
          })}
        </div>
        {!parties.size && !partidoRels.length ? (
          <Empty>Sem partidos documentados neste perfil.</Empty>
        ) : null}
      </section>
    );
  }

  if (tab === "eleicoes") {
    const elections = [...(pessoa.mandatos || [])]
      .filter((m) => m.ano_eleicao != null)
      .sort((a, b) => Number(b.ano_eleicao) - Number(a.ano_eleicao));
    return (
      <section className="panel stack">
        <h2>Eleições</h2>
        <p className="muted">
          Anos de eleição ligados aos mandatos documentados (TSE / Casa).
        </p>
        <div className="list-block">
          {elections.map((m) => (
            <div
              key={m.id || `${m.ano_eleicao}-${m.cargo}-${m.uf}`}
              className="list-item"
            >
              <p className="item-title">Eleição {m.ano_eleicao}</p>
              <p className="item-meta">
                {[m.cargo, m.uf, m.partido, m.fonte].filter(Boolean).join(" · ")}
              </p>
            </div>
          ))}
        </div>
        {pessoa.campanhas_resumo ? (
          <p className="item-meta">
            Campanha (amostra):{" "}
            {pessoa.campanhas_resumo.ano
              ? `eleição ${pessoa.campanhas_resumo.ano}`
              : "—"}
            {pessoa.campanhas_resumo.total_despesas != null
              ? ` · despesas ${formatBRL(pessoa.campanhas_resumo.total_despesas)}`
              : ""}
            {" · "}
            <button
              type="button"
              className="btn-ghost"
              onClick={() => onTab?.("dinheiro")}
            >
              Ver em Dinheiro
            </button>
          </p>
        ) : null}
        {!elections.length ? (
          <Empty>Sem anos de eleição nos mandatos deste registro.</Empty>
        ) : null}
      </section>
    );
  }

  if (tab === "mandatos") {
    const leg = pessoa.legislativo_resumo;
    const mandatosGov = (pessoa.mandatos || []).filter(Boolean);
    return (
      <section className="panel stack">
        <h2>Mandatos</h2>
        <div className="list-block">
          <div className="list-item">
            <p className="item-title">{pessoa.cargo_atual || "Cargo não informado"}</p>
            <p className="item-meta">
              {[
                pessoa.partido,
                pessoa.uf,
                pessoa.no_poder_2026
                  ? "em exercício (lista atual)"
                  : "fora de exercício neste corte",
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          {mandatosGov.map((m) => (
            <div key={m.id || `${m.cargo}-${m.uf}-${m.ano_eleicao}`} className="list-item">
              <p className="item-title">
                {m.cargo || "Mandato"}
                {m.uf ? ` · ${m.uf}` : ""}
              </p>
              <p className="item-meta">
                {[
                  m.ano_eleicao != null ? `Eleição ${m.ano_eleicao}` : null,
                  m.partido,
                  m.inicio || m.fim
                    ? `${m.inicio || "?"} → ${m.fim || "?"}`
                    : null,
                  m.fonte,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {m.uf && (m.cargo || "").toLowerCase() === "governador" ? (
                <p className="item-meta">
                  <Link
                    href={`/indicadores/uf/${String(m.uf).toUpperCase()}?ind=ind_pib_corrente${
                      m.id ? `&mandato=${encodeURIComponent(m.id)}` : ""
                    }`}
                  >
                    Indicadores durante a administração →
                  </Link>
                </p>
              ) : null}
            </div>
          ))}
          {leg?.ano_inicio_atividade ? (
            <div className="list-item">
              <p className="item-title">Atividade na amostra legislativa</p>
              <p className="item-meta">
                {leg.ano_inicio_atividade}–{leg.ano_fim_atividade ?? "—"}
                {leg.anos_atividade != null
                  ? ` · ~${leg.anos_atividade} ano(s)`
                  : ""}
              </p>
            </div>
          ) : null}
        </div>
        <p className="prose-note">
          Mandatos de governador vêm do resultado TSE (consulta_cand). Status de
          exercício federal vem da lista atual da Casa. Tempo legislativo deriva
          dos anos com voto/autoria na amostra Atlas.
        </p>
      </section>
    );
  }

  if (tab === "atuacao") {
    const lista =
      leg?.proposicoes_lista?.length
        ? leg.proposicoes_lista
        : leg?.proposicoes_sample || [];
    const porTipo = leg?.por_tipo || {};
    const sorted = [...lista].sort((a, b) => {
      if (typeof a === "string" || typeof b === "string") return 0;
      const aa = a as { data_apresentacao?: string; ano?: string | number; id?: string };
      const bb = b as { data_apresentacao?: string; ano?: string | number; id?: string };
      const da = String(aa.data_apresentacao || "");
      const db = String(bb.data_apresentacao || "");
      if (da || db) {
        if (db !== da) return db.localeCompare(da);
      }
      const ya = Number(aa.ano) || 0;
      const yb = Number(bb.ano) || 0;
      if (yb !== ya) return yb - ya;
      return String(bb.id || "").localeCompare(String(aa.id || ""));
    });
    return (
      <div className="stack">
      <section className="panel stack">
        <h2>Atuação · Projetos / proposições</h2>
        <p className="muted">
          <strong>{leg?.qtd_projetos ?? 0}</strong> projetos (PL/PEC/PLP etc.) ·{" "}
          <strong>{leg?.qtd_proposicoes ?? 0}</strong> proposições no total.
          Lista abaixo: mais recente → mais antiga
          {sorted.length < (leg?.qtd_proposicoes || 0)
            ? ` (mostrando ${sorted.length} de ${leg?.qtd_proposicoes})`
            : ""}
          .
        </p>
        {Object.keys(porTipo).length > 0 ? (
          <div className="list-block">
            {Object.entries(porTipo)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 16)
              .map(([tipo, n]) => (
                <div key={tipo} className="list-item">
                  <p className="item-title">{tipo}</p>
                  <p className="item-meta">{n} na amostra</p>
                </div>
              ))}
          </div>
        ) : null}
        <h3>Lista (nome + ano + link)</h3>
        {sorted.length > 0 ? (
          <div className="list-block">
            {sorted.slice(0, projVisible).map((s) => {
              if (typeof s === "string") {
                const url = camaraProposicaoUrl(s);
                return (
                  <div key={s} className="list-item">
                    <p className="item-title">
                      {url ? (
                        <a href={url} target="_blank" rel="noreferrer">
                          Proposição {s}
                        </a>
                      ) : (
                        s
                      )}
                    </p>
                  </div>
                );
              }
              const url = camaraProposicaoUrl(s.id);
              const nome = propLabel({
                label: s.label,
                tipo: s.tipo,
                numero: s.numero,
                ano: s.ano,
                id: s.id,
              });
              return (
                <div key={s.id || s.label} className="list-item">
                  <p className="item-title">
                    {url ? (
                      <a href={url} target="_blank" rel="noreferrer">
                        {nome}
                      </a>
                    ) : (
                      nome
                    )}
                  </p>
                  <p className="item-meta">
                    {[
                      s.tipo,
                      s.ano != null && String(s.ano) !== "0" ? `ano ${s.ano}` : null,
                      s.data_apresentacao
                        ? `apresentada ${String(s.data_apresentacao).slice(0, 10)}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    {s.ementa ? ` · ${s.ementa}` : ""}
                    {url ? " · abrir na Câmara" : ""}
                  </p>
                </div>
              );
            })}
            {projVisible < sorted.length ? (
              <button
                type="button"
                className="btn-outline"
                style={{ marginTop: 8 }}
                onClick={() => setProjVisible((n) => n + 40)}
              >
                Mostrar mais ({sorted.length - projVisible} restantes na amostra)
              </button>
            ) : null}
          </div>
        ) : autorProps.length > 0 ? (
          <div className="list-block">
            {autorProps.slice(0, 40).map((r) => {
              const other = r.origem === pessoa.id ? r.destino : r.origem;
              return (
                <div key={r.id} className="list-item">
                  <p className="item-title">
                    <Link href={hrefOther(other)}>{nameOf(other)}</Link>
                  </p>
                  <p className="item-meta">{r.periodo || ""}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty>Sem proposições de autoria nesta amostra.</Empty>
        )}
      </section>
      <section className="panel stack">
        <h2>Atuação · Votações</h2>
        <p className="prose-note">
          Votos nominais registrados na amostra — não é frequência oficial de
          plenário. Projeto no grafo não é visual principal.
        </p>
        <p className="muted">
          <strong>
            {leg?.votos_registrados ?? leg?.votacoes_nominais ?? 0}
          </strong>{" "}
          voto(s) nominal(is) na amostra
          {leg?.por_voto && Object.keys(leg.por_voto).length
            ? ` · ${Object.keys(leg.por_voto).length} tipo(s) de voto`
            : ""}
          .
        </p>
        {leg?.por_voto && Object.keys(leg.por_voto).length ? (
          <div className="list-block">
            {Object.entries(leg.por_voto)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 12)
              .map(([voto, n]) => (
                <div key={voto} className="list-item">
                  <p className="item-title">{voto || "(sem label)"}</p>
                  <p className="item-meta">{n} registro(s)</p>
                </div>
              ))}
          </div>
        ) : (
          <Empty>Sem detalhe de votos nesta amostra.</Empty>
        )}
      </section>
      </div>
    );
  }


  if (tab === "dinheiro") {
    const desp = pessoa.despesas_resumo;
    const emendas = pessoa.emendas_resumo || [];
    const forn = desp?.fornecedores || [];
    const rem = pessoa.remuneracao;
    return (
      <section className="panel stack">
        <h2>Dinheiro público</h2>
        <p className="prose-note">
          Campanhas, emendas, cota e patrimônio ficam separados — não há um
          único “valor total”. Emenda ou fornecedor não são ilegalidade por si.
          Relação documental não é culpa.
        </p>
        <div className="atlas-profile-money-grid">
        <div className="atlas-profile-money-block">
        <h3>Campanha eleitoral (TSE)</h3>
        {pessoa.campanhas_resumo ? (
          <>
            <p className="muted">
              {pessoa.campanhas_resumo.ano
                ? "Eleição " + pessoa.campanhas_resumo.ano
                : "Campanha"}
              {pessoa.campanhas_resumo.cargo
                ? " · " + pessoa.campanhas_resumo.cargo
                : ""}
              {pessoa.campanhas_resumo.uf
                ? " · " + pessoa.campanhas_resumo.uf
                : ""}
              {" · despesas contratadas: "}
              <strong>
                {formatBRL(pessoa.campanhas_resumo.total_despesas)}
              </strong>
              {pessoa.campanhas_resumo.fonte_url ? (
                <>
                  {" · "}
                  <a
                    href={pessoa.campanhas_resumo.fonte_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    fonte TSE
                  </a>
                </>
              ) : null}
            </p>
            {(pessoa.despesas_campanha || []).length > 0 ? (
              <div className="list-block">
                {(pessoa.despesas_campanha || []).slice(0, 12).map((f, i) => {
                  const cnpj = f.cnpj ? String(f.cnpj) : "";
                  const empHref =
                    cnpj.length === 14 ? "/empresas/e_cnpj_" + cnpj : null;
                  return (
                    <div key={(cnpj || f.nome || "camp") + "-" + i} className="list-item">
                      <p className="item-title">
                        {empHref ? (
                          <Link href={empHref}>{f.nome || f.cnpj}</Link>
                        ) : (
                          f.nome || f.cnpj || "Fornecedor"
                        )}
                      </p>
                      <p className="item-meta">
                        {formatBRL(f.valor)}
                        {cnpj ? " · " + cnpj : ""}
                      </p>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </>
        ) : (
          <Empty>Sem despesas de campanha nesta amostra.</Empty>
        )}
        </div>

        <div className="atlas-profile-money-block">
        <h3>Emendas</h3>
        {emendas.length ? (
          <div className="list-block">
            {emendas.slice(0, 16).map((em, i) => (
              <div
                key={(em.emenda_id || em.codigo || "") + "-" + i}
                className="list-item"
              >
                <p className="item-title">
                  {em.codigo || em.emenda_id || "Emenda"}
                  {em.ano != null ? ` · ${em.ano}` : ""}
                  {em.localidade ? ` · ${em.localidade}` : ""}
                </p>
                <p className="item-meta">
                  {em.valor != null ? formatBRL(em.valor) : ""}
                  {em.qtd_documentos != null
                    ? ` · ${em.qtd_documentos} doc(s)`
                    : ""}
                </p>
                {(em.beneficiarios || []).length > 0 ? (
                  <ul className="muted" style={{ marginTop: 4, paddingLeft: 18 }}>
                    {(em.beneficiarios || []).slice(0, 4).map((b, j) => {
                      const cnpj = b.cnpj ? String(b.cnpj) : "";
                      const label = b.nome || b.orgao || cnpj || "Beneficiário";
                      return (
                        <li key={(cnpj || label) + "-" + j}>
                          {cnpj.length === 14 ? (
                            <Link href={"/empresas/e_cnpj_" + cnpj}>{label}</Link>
                          ) : (
                            label
                          )}
                          {b.valor != null ? " · " + formatBRL(b.valor) : ""}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <Empty>Sem emendas nesta amostra.</Empty>
        )}
        </div>

        <div className="atlas-profile-money-block">
        <h3>Cota / contratos contextuais</h3>
        {desp ? (
          <>
            <p className="muted">
              Cota parlamentar ({desp.ano}) · total liquidado:{" "}
              <strong>{formatBRL(desp.total)}</strong>
              {" · "}
              {desp.qtd_lancamentos?.toLocaleString("pt-BR")} lançamentos
              {desp.completo === false ? " (amostra paginada)" : ""}.
              {desp.fonte_url ? (
                <>
                  {" "}
                  <a href={desp.fonte_url} target="_blank" rel="noreferrer">
                    {String(desp.fonte_url).includes("senado") ||
                    desp.fonte === "senado_ceaps"
                      ? "fonte Senado (CEAPS)"
                      : "fonte Câmara"}
                  </a>
                </>
              ) : null}
            </p>
            {desp.por_tipo?.length ? (
              <div className="list-block">
                {desp.por_tipo.map((t) => (
                  <div key={t.tipo} className="list-item">
                    <p className="item-title">{t.tipo}</p>
                    <p className="item-meta">{formatBRL(t.valor)}</p>
                  </div>
                ))}
              </div>
            ) : null}
            {forn.length > 0 ? (
              <>
                <h4 className="atlas-profile-money-sub">Fornecedores (amostra)</h4>
                <div className="list-block">
                  {forn.slice(0, 12).map((f, i) => {
                    const cnpj = f.cnpj ? String(f.cnpj) : "";
                    const empHref =
                      cnpj.length === 14 ? "/empresas/e_cnpj_" + cnpj : null;
                    const rowKey = (cnpj || f.nome || "forn") + "-" + i;
                    return (
                      <div key={rowKey} className="list-item">
                        <p className="item-title">
                          {empHref ? (
                            <Link href={empHref}>{f.nome || f.cnpj}</Link>
                          ) : (
                            f.nome || f.cnpj || "Fornecedor"
                          )}
                        </p>
                        <p className="item-meta">
                          {formatBRL(f.valor)}
                          {f.qtd ? " · " + f.qtd + " lançamento(s)" : ""}
                          {cnpj ? " · " + cnpj : ""}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : null}
          </>
        ) : (
          <Empty>Sem despesas de cota nesta amostra.</Empty>
        )}
        </div>

        <div className="atlas-profile-money-block">
        <h3>Patrimônio declarado</h3>
        {pessoa.bens_declarados ? (
          <>
            <p className="muted">
              {pessoa.bens_declarados.qtd?.toLocaleString("pt-BR")} bens
              {" · "}
              {formatBRL(pessoa.bens_declarados.valor_total)}
            </p>
            {pessoa.bens_declarados.amostra?.length ? (
              <div className="list-block">
                {pessoa.bens_declarados.amostra.map((b, i) => (
                  <div key={(b.tipo || "bem") + "-" + i} className="list-item">
                    <p className="item-title">{b.tipo || "Bem"}</p>
                    <p className="item-meta">{formatBRL(b.valor)}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <Empty>Sem bens declarados nesta amostra.</Empty>
        )}
        {bensRels.length > 0 ? (
          <>
            <h4 className="atlas-profile-money-sub">Ativos no grafo</h4>
            <div className="list-block">
              {bensRels.slice(0, 12).map((r) => {
                const other = r.origem === pessoa.id ? r.destino : r.origem;
                return (
                  <div key={r.id} className="list-item">
                    <p className="item-title">
                      <Link href={hrefOther(other)}>{nameOf(other)}</Link>
                    </p>
                    <p className="item-meta">{r.periodo || r.contexto || ""}</p>
                  </div>
                );
              })}
            </div>
          </>
        ) : null}
        </div>

        <div className="atlas-profile-money-block">
        <h3>Remuneração (série do cargo)</h3>
        {rem?.serie_subsidio?.length ? (
          <>
            <p className="muted">
              Série macro do cargo ({rem.cargo?.replaceAll("_", " ")}), não o
              holerite individual.
            </p>
            <div className="list-block">
              {rem.serie_subsidio.map((s) => (
                <div key={s.ano} className="list-item">
                  <p className="item-title">{s.ano}</p>
                  <p className="item-meta">
                    {formatBRL(s.subsidio_mensal)}
                    {s.fonte_url ? (
                      <>
                        {" · "}
                        <a href={s.fonte_url} target="_blank" rel="noreferrer">
                          fonte
                        </a>
                      </>
                    ) : null}
                  </p>
                </div>
              ))}
            </div>
            {rem.aviso ? <p className="prose-note">{rem.aviso}</p> : null}
          </>
        ) : (
          <Empty>Sem série de subsídio nesta amostra.</Empty>
        )}
        </div>
        </div>
      </section>
    );
  }


  if (tab === "relacoes") {
    return (
      <div className="stack">
        <section className="panel stack">
          <h2>Relações ({rels.length})</h2>
          <p className="prose-note">
            Cada aresta exige justificativa documental. Relação não é acusação.
            O grafo abaixo é complementar — não é a visualização principal de
            emendas ou dinheiro.
          </p>
          {rels.length ? (
            <div className="list-block">
              {rels.slice(0, 60).map((r) => {
                const other = r.origem === pessoa.id ? r.destino : r.origem;
                return (
                  <div key={r.id} className="list-item">
                    <p className="item-title">
                      {r.tipo.replace(/_/g, " ")} →{" "}
                      <Link href={hrefOther(other)}>{nameOf(other)}</Link>
                    </p>
                    <p className="item-meta">
                      {r.periodo || ""}
                      {r.grau_confirmacao ? ` · ${r.grau_confirmacao}` : ""}
                    </p>
                    <p className="faint">
                      {r.justificativa_documental || r.contexto || ""}
                    </p>
                  </div>
                );
              })}
            </div>
          ) : (
            <Empty>Sem relações nesta amostra.</Empty>
          )}
          {empresaRels.length ? (
            <>
              <h3>Empresas e contratos contextuais</h3>
              <div className="list-block">
                {empresaRels.slice(0, 40).map((r) => {
                  const other = r.origem === pessoa.id ? r.destino : r.origem;
                  return (
                    <div key={r.id} className="list-item">
                      <p className="item-title">
                        {r.tipo.replace(/_/g, " ")} →{" "}
                        <Link href={hrefOther(other)}>{nameOf(other)}</Link>
                      </p>
                      <p className="item-meta">
                        {[r.periodo, r.grau_confirmacao]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                      <p className="faint">
                        {r.justificativa_documental || r.contexto || r.nota || ""}
                      </p>
                    </div>
                  );
                })}
              </div>
            </>
          ) : null}
          {frentes.length ? (
            <>
              <h3>Frentes / órgãos</h3>
              <div className="list-block">
                {frentes.slice(0, 20).map((r) => {
                  const other = r.origem === pessoa.id ? r.destino : r.origem;
                  return (
                    <div key={r.id} className="list-item">
                      <p className="item-title">
                        <Link href={hrefOther(other)}>{nameOf(other)}</Link>
                      </p>
                      <p className="item-meta">{r.contexto || "membro"}</p>
                    </div>
                  );
                })}
              </div>
            </>
          ) : null}
        </section>
        <section className="panel stack">
          <h2>Mapa de relações (amostra)</h2>
          <ProfileMicroGraph
            centro={pessoa.id}
            nodes={graphNodes}
            edges={graphEdges}
          />
        </section>
      </div>
    );
  }

  if (tab === "justica") {
    return (
      <section className="panel stack">
        <h2>Justiça / processos</h2>
        <p className="prose-note">
          Citação ou menção não equivalem a condenação. Só entram arestas com peça
          e fonte.
        </p>
        {regs.length === 0 && mentioned.length === 0 ? (
          <Empty>
            Sem registros pessoa–caso nem menções nesta amostra. Investigações
            judiciais entram quando houver peça pública.
          </Empty>
        ) : (
          <>
            {regs.map((r) => (
              <div key={r.id} className="list-item">
                <Link href={`/casos/${r.caso_id}`} className="item-title">
                  {casos[r.caso_id]?.nome || r.caso_id}
                </Link>
                <p className="item-meta">
                  <span className={`badge badge-${r.status}`}>
                    {STATUS_LABEL[r.status || ""] || r.status}
                  </span>{" "}
                  · camada {r.camada}
                </p>
                <p className="muted">{r.acusacao}</p>
              </div>
            ))}
            {mentioned.length > 0 ? (
              <>
                <h3>Menções documentais</h3>
                <div className="list-block">
                  {mentioned.slice(0, 20).map((r) => {
                    const other = r.origem === pessoa.id ? r.destino : r.origem;
                    return (
                      <div key={r.id} className="list-item">
                        <p className="item-title">
                          <Link href={hrefOther(other)}>{nameOf(other)}</Link>
                        </p>
                        <p className="item-meta">
                          {r.justificativa_documental || r.contexto || ""}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : null}
          </>
        )}
      </section>
    );
  }

  if (tab === "documentos") {
    return (
      <section className="panel stack">
        <h2>Documentos / fontes</h2>
        {fontes.length ? (
          <ul className="plain-list">
            {fontes.map((f) => (
              <li key={f}>
                <a href={f} target="_blank" rel="noreferrer" className="muted">
                  {f}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Sem documentos/URLs de fonte neste perfil.</Empty>
        )}
        {pessoa.redes_sociais?.length ? (
          <>
            <h3>Redes (declaradas na Casa)</h3>
            <div className="chips">
              {pessoa.redes_sociais.map((u) => (
                <a
                  key={u}
                  className="chip"
                  href={u}
                  target="_blank"
                  rel="noreferrer"
                >
                  {u.replace(/^https?:\/\//, "").slice(0, 40)}
                </a>
              ))}
            </div>
          </>
        ) : null}
      </section>
    );
  }

  return null;
}
