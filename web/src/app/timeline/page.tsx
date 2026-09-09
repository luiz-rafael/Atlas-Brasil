import Link from "next/link";
import { getKB } from "@/lib/kb";

function colorForEixo(eixo?: string) {
  const e = (eixo || "").toLowerCase();
  if (e.includes("dinheiro") || e.includes("contrato")) return "#B08B44";
  if (e.includes("crime") || e.includes("investig")) return "#76667F";
  if (e.includes("judici") || e.includes("stf")) return "#55738B";
  if (e.includes("eleitor") || e.includes("polit")) return "#D5C7A4";
  if (e.includes("midia") || e.includes("imprensa")) return "#8B6C91";
  return "#315D78";
}

export default function TimelinePage({
  searchParams,
}: {
  searchParams: { eixo?: string; governo_id?: string; ano?: string };
}) {
  const kb = getKB();
  let items = [...kb.timeline].sort((a, b) =>
    String(a.data).localeCompare(String(b.data))
  );
  if (searchParams.eixo)
    items = items.filter((t) => t.eixo === searchParams.eixo);
  if (searchParams.governo_id)
    items = items.filter((t) => t.governo_id === searchParams.governo_id);
  if (searchParams.ano)
    items = items.filter((t) => String(t.data).startsWith(searchParams.ano!));

  const eixos = Array.from(new Set(kb.timeline.map((t) => t.eixo))).sort();
  const years = Array.from(
    new Set(kb.timeline.map((t) => String(t.data).slice(0, 4)))
  ).sort();

  return (
    <div className="stack">
      <div className="dash-head">
        <div>
          <h1 className="section-title">Linha do Tempo</h1>
          <p className="muted">
            Veja a evolução dos eventos, relações e documentos ao longo do tempo.{" "}
            <Link href="/timeline/como-chegamos" style={{ color: "var(--cyan)" }}>
              Como chegamos?
            </Link>
          </p>
        </div>
        <form className="filters" method="get">
          {searchParams.ano ? (
            <input type="hidden" name="ano" value={searchParams.ano} />
          ) : null}
          <select name="eixo" defaultValue={searchParams.eixo || ""}>
            <option value="">Todos os eventos</option>
            {eixos.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
          <button className="btn" type="submit">
            Filtrar
          </button>
        </form>
      </div>

      <div className="year-rail">
        <Link
          href="/timeline"
          className={`year-pill ${!searchParams.ano ? "active" : ""}`}
        >
          Todos
        </Link>
        {years.map((y) => (
          <Link
            key={y}
            href={`/timeline?ano=${y}${searchParams.eixo ? `&eixo=${searchParams.eixo}` : ""}`}
            className={`year-pill ${searchParams.ano === y ? "active" : ""}`}
          >
            {y}
          </Link>
        ))}
      </div>

      <div className="panel">
        <div className="tl-rich">
          {items.map((t) => {
            const c = colorForEixo(t.eixo);
            return (
              <div key={t.id} className="tl-event">
                <div className="tl-date">
                  <div>{String(t.data).slice(0, 4)}</div>
                  <div>{t.data}</div>
                </div>
                <div className="tl-rail">
                  <span className="tl-diamond" style={{ background: c, color: c }} />
                </div>
                <div>
                  <p className="item-title" style={{ margin: 0 }}>
                    {t.titulo}
                  </p>
                  <p className="muted" style={{ margin: "0.25rem 0 0", fontSize: "0.9rem" }}>
                    {t.eixo}
                    {t.governo_id ? ` · ${t.governo_id}` : ""}
                  </p>
                  {(t.fontes || []).length > 0 ? (
                    <p className="faint" style={{ margin: "0.25rem 0 0" }}>
                      Fonte: {(t.fontes || []).join("; ")}
                    </p>
                  ) : null}
                  {(t.caso_ids || []).map((cid) => (
                    <Link
                      key={cid}
                      href={`/casos/${cid}`}
                      className="chip"
                      style={{ display: "inline-block", marginTop: 6 }}
                    >
                      Ver caso
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
          {items.length === 0 ? <p className="muted">Nenhum evento neste filtro.</p> : null}
        </div>
      </div>
    </div>
  );
}
