import Link from "next/link";
import { shortestPath, PATH_DISCLAIMER } from "@/lib/graph-engine";
import { getKB, labelOf } from "@/lib/kb";

export default function ConexaoPage({
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
  const result = shortestPath(a, b, 6);

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Encontrar conexão</h1>
        <p className="muted">
          Caminho mais curto e alternativas entre duas entidades.
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
          Buscar caminho
        </button>
      </form>

      <p className="prose-note">{PATH_DISCLAIMER}</p>

      {!result.found ? (
        <p className="muted">
          Nenhum caminho documentado entre {labelOf(a)} e {labelOf(b)} com até 6
          saltos.
        </p>
      ) : (
        result.paths.map((p, idx) => (
          <section key={idx} className="list-block">
            <h2 className="section-title" style={{ fontSize: "1.1rem" }}>
              Caminho {idx + 1} · {p.resumo.nos} nós · {p.resumo.relacoes}{" "}
              relações
            </h2>
            <p className="item-meta">
              Tipos: {p.resumo.tipos.join(", ")}
            </p>
            <p className="muted" style={{ lineHeight: 1.8 }}>
              {p.nos.map((n, i) => (
                <span key={n.id}>
                  {i > 0 ? " → " : ""}
                  <Link href={`/grafo?centro=${n.id}`}>{n.nome}</Link>
                </span>
              ))}
            </p>
            <div className="list-block" style={{ marginTop: "0.5rem" }}>
              {p.edges.map((e) => (
                <div key={e.id} className="list-item">
                  <p className="item-title">{e.tipo}</p>
                  <p className="muted">{e.justificativa_documental}</p>
                  <p className="faint">
                    {e.grau_confirmacao} · {(e.fonte_ids || []).join(", ")}
                  </p>
                </div>
              ))}
            </div>
          </section>
        ))
      )}

      <p className="faint">
        <Link href={`/grafo/encontros?a=${a}&b=${b}`}>
          Ver pontos de encontro
        </Link>
        {" · "}
        <Link href="/grafo">Voltar ao grafo</Link>
      </p>
    </div>
  );
}
