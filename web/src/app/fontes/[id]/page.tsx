import Link from "next/link";
import { notFound } from "next/navigation";
import { casoById, getKB } from "@/lib/kb";

export default function FontePage({ params }: { params: { id: string } }) {
  const doc = (getKB().documentos || []).find((d) => d.id === params.id);
  if (!doc) notFound();
  const url = doc.url || doc.url_ref;

  return (
    <div className="page stack">
      <div>
        <p className="faint">Documento / fonte</p>
        <h1 className="section-title">{doc.titulo}</h1>
        <p className="muted">
          <span className="badge">{doc.nivel_fonte || "—"}</span>
          {doc.orgao ? ` · ${doc.orgao}` : ""}
          {doc.tipo ? ` · ${doc.tipo}` : ""}
          {doc.data ? ` · ${doc.data}` : ""}
        </p>
      </div>

      {url ? (
        <p className="muted">
          Link:{" "}
          {url.startsWith("http") ? (
            <a href={url} target="_blank" rel="noreferrer">
              {url}
            </a>
          ) : (
            <span>{url} (completar HTTPS)</span>
          )}
        </p>
      ) : (
        <p className="prose-note">URL pendente — fonte indexada sem link direto.</p>
      )}

      {doc.casos?.length ? (
        <section className="stack">
          <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
            Casos relacionados
          </h2>
          <div className="list-block">
            {doc.casos.map((cid) => (
              <Link key={cid} href={`/casos/${cid}`} className="list-item">
                <span className="item-title">
                  {casoById(cid)?.nome || cid}
                </span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <p className="faint">
        <Link href="/fontes">Todas as fontes</Link>
      </p>
    </div>
  );
}
