import Link from "next/link";
import { notFound } from "next/navigation";
import { entityById, formatBRL, labelOf, relacoesDe } from "@/lib/kb";

function hrefEntidade(id: string) {
  if (id.startsWith("p_")) return `/pessoas/${id}`;
  if (id.startsWith("ctr_")) return `/grafo?centro=${id}`;
  if (id.startsWith("e_cnpj_")) return `/empresas/${id}`;
  if (id.startsWith("pt_")) return `/partidos/${id}`;
  return `/grafo?centro=${id}`;
}

export default function EmpresaPage({ params }: { params: { id: string } }) {
  const empresa = entityById(params.id);
  if (!empresa || empresa.tipo !== "empresa") notFound();
  const rels = relacoesDe(empresa.id);
  const contratos = rels.filter((r) => r.tipo === "fornecido_por");

  return (
    <div className="stack" style={{ animation: "rise 0.45s ease both" }}>
      <div className="profile-hero">
        <div className="avatar" aria-hidden>
          ▣
        </div>
        <div className="profile-meta">
          <p className="eyebrow">
            Empresa · dados públicos
            {(empresa.tags || []).includes("sancionada") ? " · sancionada (CGU)" : ""}
          </p>
          <h1>{empresa.nome}</h1>
          <p>
            {empresa.cnpj ? `CNPJ ${empresa.cnpj}` : "CNPJ não informado"}
            {empresa.rfb_status ? ` · RFB: ${empresa.rfb_status}` : ""}
          </p>
          {(empresa.tags || []).includes("sancionada") ? (
            <div className="chips" style={{ marginTop: 8 }}>
              <span className="chip" style={{ borderColor: "#8a3b2e", color: "#8a3b2e" }}>
                Sancionada (CEIS/CNEP)
              </span>
              {empresa.sancao_resumo?.tipo ? (
                <span className="chip">{empresa.sancao_resumo.tipo}</span>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="profile-actions">
          <Link
            className="btn-outline accent"
            href={`/grafo?centro=${encodeURIComponent(empresa.id)}`}
          >
            Ver no grafo
          </Link>
          <Link className="btn-primary" href="/investigar" style={{ display: "inline-flex" }}>
            Adicionar à análise
          </Link>
        </div>
      </div>

      <div className="tabs">
        <span className="active">Visão geral</span>
        <Link href={`/grafo?centro=${empresa.id}`}>Relações</Link>
        <Link href="/fontes">Documentos</Link>
        <Link href="/dinheiro">Contratos / dinheiro</Link>
      </div>

      <div className="indicator-grid">
        <div className="indicator">
          <div className="n">{empresa.contratos_count ?? contratos.length}</div>
          <div className="l">Contratos PNCP (amostra)</div>
        </div>
        <div className="indicator">
          <div className="n">
            {empresa.valor_contratos != null
              ? formatBRL(empresa.valor_contratos).replace(/\s/g, "\u00a0")
              : "—"}
          </div>
          <div className="l">Valor agregado amostra</div>
        </div>
        <div className="indicator">
          <div className="n">{rels.length}</div>
          <div className="l">Relações documentadas</div>
        </div>
      </div>

      <section className="panel">
        <h2>Contratos / relações</h2>
        <p className="prose-note">
          Contrato público ou doação legal não são automaticamente corrupção.
        </p>
        <div className="list-block" style={{ marginTop: "1rem" }}>
          {rels.map((r) => {
            const other = r.origem === empresa.id ? r.destino : r.origem;
            return (
              <div key={r.id} className="list-item">
                <p className="item-title">
                  {r.tipo} ·{" "}
                  <Link href={hrefEntidade(other)}>{labelOf(other)}</Link>
                </p>
                <p className="faint">{r.justificativa_documental}</p>
              </div>
            );
          })}
          {rels.length === 0 ? <p className="muted">Sem relações nesta KB.</p> : null}
        </div>
      </section>
    </div>
  );
}
