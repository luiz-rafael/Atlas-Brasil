import Link from "next/link";
import { meetingPoints, PATH_DISCLAIMER } from "@/lib/graph-engine";
import { getKB, labelOf } from "@/lib/kb";

export default function EncontrosPage({
  searchParams,
}: {
  searchParams: { a?: string; b?: string };
}) {
  const kb = getKB();
  const options = [
    ...kb.entidades.filter((e) => !e.isolada),
    ...kb.casos.map((c) => ({ id: c.id, nome: c.nome, tipo: "caso" })),
  ];
  const a = searchParams.a || "p_lula";
  const b = searchParams.b || "p_jair";
  const result = meetingPoints(a, b, 2);

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Onde as redes se encontram?</h1>
        <p className="muted">
          Interseção das redes de {labelOf(a)} e {labelOf(b)} (ego depth 2).{" "}
          {result.total} pontos.
        </p>
      </div>

      <form className="filters" method="get">
        <select name="a" defaultValue={a}>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.nome}
            </option>
          ))}
        </select>
        <select name="b" defaultValue={b}>
          {options.map((o) => (
            <option key={`b-${o.id}`} value={o.id}>
              {o.nome}
            </option>
          ))}
        </select>
        <button className="btn" type="submit">
          Calcular
        </button>
      </form>

      <p className="prose-note">{PATH_DISCLAIMER}</p>

      {result.total === 0 ? (
        <p className="muted">Nenhuma interseção neste raio.</p>
      ) : (
        Object.entries(result.pontos).map(([tipo, nodes]) => (
          <section key={tipo} className="list-block">
            <h2
              className="section-title"
              style={{ fontSize: "1.1rem", textTransform: "uppercase" }}
            >
              {tipo} ({nodes.length})
            </h2>
            {nodes.map((n) => (
              <Link
                key={n.id}
                href={`/grafo?centro=${n.id}`}
                className="list-item"
              >
                <span className="item-title">{n.nome}</span>
                <span className="item-meta">{n.tipo}</span>
              </Link>
            ))}
          </section>
        ))
      )}

      <p className="faint">
        <Link href={`/grafo/conexao?a=${a}&b=${b}`}>Ver caminhos</Link>
        {" · "}
        <Link href="/grafo">Voltar ao grafo</Link>
      </p>
    </div>
  );
}
