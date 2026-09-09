import Link from "next/link";
import { getKB } from "@/lib/kb";

export default function ComoChegamosPage({
  searchParams,
}: {
  searchParams: { evento_id?: string };
}) {
  const kb = getKB();
  const items = [...(kb.timeline || [])].sort((a, b) =>
    String(a.data).localeCompare(String(b.data))
  );
  const eventoId = searchParams.evento_id || items[items.length - 1]?.id;
  const idx = items.findIndex((t) => t.id === eventoId);
  const chain = idx >= 0 ? items.slice(0, idx + 1) : items;

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Como chegamos até aqui?</h1>
        <p className="muted">
          Cadeia temporal até o evento selecionado ({chain.length} marcos).
        </p>
      </div>

      <form className="filters" method="get">
        <select name="evento_id" defaultValue={eventoId}>
          {items.map((t) => (
            <option key={t.id} value={t.id}>
              {t.data} — {t.titulo}
            </option>
          ))}
        </select>
        <button className="btn" type="submit">Ver cadeia</button>
      </form>

      <div className="timeline">
        {chain.map((t) => (
          <div
            key={t.id}
            className="timeline-item"
            style={
              t.id === eventoId
                ? { borderLeftColor: "var(--accent)" }
                : undefined
            }
          >
            <p className="faint">
              {t.data} · {t.eixo}
            </p>
            <p className="item-title">{t.titulo}</p>
            {t.caso_ids?.length ? (
              <p className="item-meta">
                {t.caso_ids.map((cid, i) => (
                  <span key={cid}>
                    {i > 0 ? ", " : ""}
                    <Link href={`/casos/${cid}`}>{cid}</Link>
                  </span>
                ))}
              </p>
            ) : null}
          </div>
        ))}
      </div>

      <p className="faint">
        <Link href="/timeline">Linha do tempo completa</Link>
      </p>
    </div>
  );
}
