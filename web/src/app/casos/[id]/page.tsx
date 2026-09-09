import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchCasoDetail } from "@/lib/casos";
import {
  casoById,
  documentos,
  dossieDe,
  getKB,
  registrosDeCaso,
  STATUS_LABEL,
} from "@/lib/kb";

export default async function CasoPage({ params }: { params: { id: string } }) {
  const api = await fetchCasoDetail(params.id);

  if (api?.caso) {
    const caso = api.caso;
    const regs = api.regs || [];
    const pessoas = api.pessoas || {};
    return (
      <div className="stack">
        <div className="profile-hero">
          <div className="avatar" aria-hidden>
            ☰
          </div>
          <div className="profile-meta">
            <p className="eyebrow">Caso / operação · {api.source || "api"}</p>
            <h1>{caso.nome}</h1>
            <p>
              {(caso.periodo as string) || "Período em construção"}
              {Array.isArray(caso.eixos) && caso.eixos.length
                ? ` · ${(caso.eixos as string[]).join(" · ")}`
                : ""}
            </p>
          </div>
          <div className="profile-actions">
            <Link className="btn-outline accent" href="/grafo">
              Ver no grafo
            </Link>
          </div>
        </div>
        <p className="prose-note">
          {api.disclaimer ||
            "O Atlas documenta. Dossiê ou menção ≠ culpa automática."}
        </p>
        <section className="panel stack">
          <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
            Pessoas ligadas ({regs.length})
          </h2>
          <div className="list-block">
            {regs.map((r) => {
              const pid = String(r.pessoa_id || "");
              const p = pessoas[pid];
              const status = String(r.status || "");
              return (
                <Link
                  key={`${pid}-${r.caso_id}`}
                  href={pid ? `/pessoas/${pid}` : "#"}
                  className="list-item"
                >
                  <span className="item-title">
                    {p?.nome || pid || "—"}
                  </span>
                  <span className="item-meta">
                    {p?.partido || "—"}
                    {status
                      ? ` · ${STATUS_LABEL[status] || status}`
                      : ""}
                  </span>
                </Link>
              );
            })}
            {!regs.length ? (
              <p className="muted">Sem registros pessoa↔caso neste serving.</p>
            ) : null}
          </div>
        </section>
        <p className="faint">
          Timeline/documentos ricos ainda podem complementar via KB no grafo.
        </p>
      </div>
    );
  }

  // Fallback KB
  const caso = casoById(params.id);
  if (!caso) notFound();
  const d = dossieDe(caso.id);
  const kb = getKB();
  const regs = registrosDeCaso(caso.id);
  const docs = documentos({ caso_id: caso.id });

  return (
    <div className="stack">
      <div className="profile-hero">
        <div className="avatar" aria-hidden>
          ☰
        </div>
        <div className="profile-meta">
          <p className="eyebrow">Caso / operação · kb_fallback</p>
          <h1>{caso.nome}</h1>
          <p>
            {caso.periodo || "Período em construção"}
            {caso.eixos?.length ? ` · ${caso.eixos.join(" · ")}` : ""}
          </p>
        </div>
      </div>
      {d?.status_atual ? (
        <p className="prose-note">
          <strong>Status atual:</strong> {d.status_atual}
        </p>
      ) : null}
      <section className="panel stack">
        <h2>Atores ({regs.length})</h2>
        <div className="list-block">
          {regs.map((r) => (
            <Link
              key={`${r.pessoa_id}-${r.caso_id}`}
              href={`/pessoas/${r.pessoa_id}`}
              className="list-item"
            >
              <span className="item-title">{r.pessoa_id}</span>
              <span className="item-meta">
                {STATUS_LABEL[r.status] || r.status}
              </span>
            </Link>
          ))}
        </div>
      </section>
      <p className="muted">
        Documentos: {docs.length} · Fluxos:{" "}
        {(kb.fluxos_financeiros || []).filter((f) => f.caso_id === caso.id)
          .length}
      </p>
    </div>
  );
}
