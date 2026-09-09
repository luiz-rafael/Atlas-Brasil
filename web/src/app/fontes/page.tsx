import Link from "next/link";
import { casoById, documentosServing } from "@/lib/kb";

const NIVEIS = [
  { value: "1_primaria", label: "1 — Primária" },
  { value: "2_jornalismo", label: "2 — Jornalismo" },
  { value: "3_academica", label: "3 — Acadêmica" },
  { value: "4_outras", label: "4 — Outras" },
];

function docStyle(tipo?: string, nivel?: string) {
  const t = (tipo || "").toLowerCase();
  if (t.includes("contrat")) return { bg: "rgba(234,179,8,0.18)", fg: "#fbbf24", label: "CTR" };
  if (t.includes("relator")) return { bg: "rgba(167,139,250,0.18)", fg: "#c4b5fd", label: "REL" };
  if (nivel === "2_jornalismo" || t.includes("report"))
    return { bg: "rgba(56,189,248,0.18)", fg: "#7dd3fc", label: "MID" };
  if (t.includes("denunc") || t.includes("senten") || t.includes("acord") || t.includes("hc"))
    return { bg: "rgba(244,63,94,0.18)", fg: "#fb7185", label: "JUD" };
  return { bg: "rgba(34,197,94,0.15)", fg: "#4ade80", label: "DOC" };
}

export default async function FontesPage({
  searchParams,
}: {
  searchParams: { nivel?: string; orgao?: string; q?: string };
}) {
  const docs = await documentosServing({
    nivel: searchParams.nivel,
    orgao: searchParams.orgao,
    q: searchParams.q,
  });

  return (
    <div className="stack">
      <div>
        <h1 className="section-title">Documentos</h1>
        <p className="muted">
          Acesse os documentos originais e metadados da KB. Tudo correlacionado a
          casos e entidades quando houver `fonte_ids`.
        </p>
      </div>

      <section
        id="cobertura"
        className="panel stack"
        style={{ scrollMarginTop: 120 }}
      >
        <h2>Cobertura das fontes</h2>
        <p className="muted">
          Documentos indexados nesta base vêm de órgãos públicos, dados abertos e
          peças com URL. Lacunas são esperadas: ausência de documento ≠ ausência
          de fato. Veja também a{" "}
          <Link href="/metodologia">metodologia</Link> e o{" "}
          <Link href="/status">status</Link> da coleta.
        </p>
      </section>

      <form className="filters" method="get">
        <input
          name="q"
          defaultValue={searchParams.q || ""}
          placeholder="Buscar documentos…"
        />
        <select name="nivel" defaultValue={searchParams.nivel || ""}>
          <option value="">Todos os níveis</option>
          {NIVEIS.map((n) => (
            <option key={n.value} value={n.value}>
              {n.label}
            </option>
          ))}
        </select>
        <input
          name="orgao"
          defaultValue={searchParams.orgao || ""}
          placeholder="Órgão"
        />
        <button className="btn" type="submit">
          Filtros
        </button>
      </form>

      <div className="panel">
        {docs.map((doc) => {
          const url = doc.url || doc.url_ref;
          const st = docStyle(doc.tipo, doc.nivel_fonte);
          const oficial = doc.nivel_fonte === "1_primaria";
          return (
            <div key={doc.id} className="doc-row">
              <div className="doc-ico" style={{ background: st.bg, color: st.fg }}>
                {st.label}
              </div>
              <div>
                <p className="item-title" style={{ margin: 0 }}>
                  <Link href={`/fontes/${doc.id}`}>{doc.titulo}</Link>
                </p>
                <p className="item-meta" style={{ margin: "0.25rem 0 0" }}>
                  {doc.tipo || "documento"}
                  {doc.orgao ? ` · ${doc.orgao}` : ""}
                  {doc.data ? ` · ${doc.data}` : ""}
                </p>
                {doc.casos?.length ? (
                  <p className="faint" style={{ margin: "0.2rem 0 0" }}>
                    Casos:{" "}
                    {doc.casos.map((cid, i) => (
                      <span key={cid}>
                        {i > 0 ? ", " : ""}
                        <Link href={`/casos/${cid}`}>
                          {casoById(cid)?.nome || cid}
                        </Link>
                      </span>
                    ))}
                  </p>
                ) : null}
              </div>
              <div className="doc-actions">
                <span className={`badge ${oficial ? "badge-absolvido" : "badge-investigado"}`}>
                  {oficial ? "Oficial" : "Secundária"}
                </span>
                {url?.startsWith("http") ? (
                  <a href={url} target="_blank" rel="noreferrer">
                    {oficial ? "PDF / Link" : "Link"}
                  </a>
                ) : (
                  <Link href={`/fontes/${doc.id}`}>Detalhe</Link>
                )}
              </div>
            </div>
          );
        })}
        {docs.length === 0 ? <p className="muted">Nenhum documento.</p> : null}
      </div>
    </div>
  );
}
