import Link from "next/link";
import { getKB, labelOf } from "@/lib/kb";
import { meetingPoints, shortestPath, PATH_DISCLAIMER } from "@/lib/graph-engine";

export default function CompararPage({
  searchParams,
}: {
  searchParams: { a?: string; b?: string };
}) {
  const kb = getKB();
  const options = [
    ...kb.entidades.filter((e) => !e.isolada),
    ...kb.casos.map((c) => ({ id: c.id, nome: c.nome })),
  ];
  const a = searchParams.a || "p_lula";
  const b = searchParams.b || "p_jair";
  const enc = meetingPoints(a, b, 2);
  const path = shortestPath(a, b, 6);

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Comparar redes</h1>
        <p className="muted">
          {labelOf(a)} × {labelOf(b)} — interseção e caminhos documentados.
        </p>
      </div>

      <form className="filters" method="get">
        <select name="a" defaultValue={a}>
          {options.map((o) => (
            <option key={o.id} value={o.id}>{o.nome}</option>
          ))}
        </select>
        <select name="b" defaultValue={b}>
          {options.map((o) => (
            <option key={`b-${o.id}`} value={o.id}>{o.nome}</option>
          ))}
        </select>
        <button className="btn" type="submit">Comparar</button>
      </form>

      <p className="prose-note">
        Interseção ≠ aliança. {PATH_DISCLAIMER}
      </p>

      <section className="list-block">
        <h2 className="section-title" style={{ fontSize: "1.1rem" }}>
          Pontos de encontro ({enc.total})
        </h2>
        {Object.entries(enc.pontos).map(([tipo, nodes]) => (
          <div key={tipo} className="list-item">
            <p className="item-title">{tipo}</p>
            <div className="chips">
              {nodes.map((n) => (
                <Link key={n.id} className="chip" href={`/grafo?centro=${n.id}`}>
                  {n.nome}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="list-block">
        <h2 className="section-title" style={{ fontSize: "1.1rem" }}>
          Caminhos ({path.paths.length})
        </h2>
        {path.paths.map((p, i) => (
          <div key={i} className="list-item">
            <p className="muted">
              {p.nos.map((n, j) => (
                <span key={n.id}>
                  {j > 0 ? " → " : ""}
                  <Link href={`/grafo?centro=${n.id}`}>{n.nome}</Link>
                </span>
              ))}
            </p>
            <p className="faint">
              {p.resumo.nos} nós · tipos: {p.resumo.tipos.join(", ")}
            </p>
          </div>
        ))}
        {!path.found ? <p className="muted">Sem caminho até 6 saltos.</p> : null}
      </section>

      <p className="faint">
        <Link href={`/grafo/conexao?a=${a}&b=${b}`}>Só caminhos</Link>
        {" · "}
        <Link href={`/grafo/encontros?a=${a}&b=${b}`}>Só encontros</Link>
      </p>
    </div>
  );
}
