import Link from "next/link";
import { detectCommunities, findBridges } from "@/lib/network-metrics";

export default function ComunidadesPage({
  searchParams,
}: {
  searchParams: { de?: string; ate?: string; view?: string };
}) {
  const de = searchParams.de;
  const ate = searchParams.ate;
  const view = searchParams.view || "comunidades";
  const com = detectCommunities({ de, ate });
  const pontes = findBridges({ de, ate });

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Comunidades e pontes</h1>
        <p className="muted">
          Detecção por label propagation. Pontes = alta intermediação entre
          grupos.
        </p>
      </div>

      <form className="filters" method="get">
        <input name="de" defaultValue={de || ""} placeholder="De (ano)" />
        <input name="ate" defaultValue={ate || ""} placeholder="Até (ano)" />
        <select name="view" defaultValue={view}>
          <option value="comunidades">Comunidades</option>
          <option value="pontes">Pontes</option>
        </select>
        <button className="btn" type="submit">
          Atualizar
        </button>
      </form>

      <p className="prose-note">{pontes.disclaimer}</p>

      {view === "pontes" ? (
        <div className="list-block">
          <h2 className="section-title" style={{ fontSize: "1.1rem" }}>
            Quem conecta esses grupos?
          </h2>
          {pontes.bridges.map((b) => (
            <Link
              key={b.id}
              href={`/grafo?centro=${b.id}&profundidade=2`}
              className="list-item"
            >
              <span className="item-title">
                #{b.rank} {b.nome}
              </span>
              <span className="item-meta">
                {b.tipo} · betweenness {b.betweenness}
              </span>
            </Link>
          ))}
          {pontes.bridges.length === 0 ? (
            <p className="muted">Nenhuma ponte detectada neste filtro.</p>
          ) : null}
        </div>
      ) : (
        com.communities.map((c) => (
          <section key={c.id} className="list-block">
            <h2 className="section-title" style={{ fontSize: "1.1rem" }}>
              {c.id} · {c.size} membros
            </h2>
            <div className="chips">
              {c.membros.map((m) => (
                <Link
                  key={m.id}
                  className="chip"
                  href={`/grafo?centro=${m.id}`}
                >
                  {m.nome}
                </Link>
              ))}
            </div>
          </section>
        ))
      )}

      {view !== "pontes" && com.communities.length === 0 ? (
        <p className="muted">Nenhuma comunidade com 2+ nós.</p>
      ) : null}

      <p className="faint">
        <Link href="/grafo/hubs">Hubs</Link>
        {" · "}
        <Link href="/grafo/encontros">Pontos de encontro</Link>
        {" · "}
        <Link href="/grafo">Grafo</Link>
      </p>
    </div>
  );
}
