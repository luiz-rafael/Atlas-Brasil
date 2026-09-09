import Link from "next/link";
import { getKB } from "@/lib/kb";
import { PATH_DISCLAIMER } from "@/lib/graph-engine";

export default function CrimePage() {
  const kb = getKB();
  const faccoes = kb.entidades.filter(
    (e) => e.tipo === "faccao" || e.tipo === "organizacao_criminosa"
  );
  const ops = kb.entidades.filter((e) => e.tipo === "operacao");

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Crime organizado</h1>
        <p className="muted">
          Módulo documental. Mapear ≠ acusar. Sem aresta crime↔política sem peça
          nominal.
        </p>
      </div>

      <p className="prose-note">
        {PATH_DISCLAIMER} Proximidade, citação ou coincidência temporal não
        provam associação criminosa.
      </p>

      <section className="list-block">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Facções / organizações (scaffold)
        </h2>
        {faccoes.map((f) => (
          <Link key={f.id} href={`/grafo?centro=${f.id}`} className="list-item">
            <span className="item-title">{f.nome}</span>
            <span className="item-meta">
              {f.tipo}
              {f.nota ? ` · ${f.nota}` : ""}
            </span>
          </Link>
        ))}
        {faccoes.length === 0 ? (
          <p className="muted">Nenhuma organização indexada ainda.</p>
        ) : null}
      </section>

      <section className="list-block">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Operações
        </h2>
        {ops.map((o) => (
          <Link key={o.id} href={`/grafo?centro=${o.id}`} className="list-item">
            <span className="item-title">{o.nome}</span>
          </Link>
        ))}
      </section>

      <section className="stack">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Regras do módulo
        </h2>
        <ul className="muted" style={{ lineHeight: 1.7, paddingLeft: "1.2rem" }}>
          <li>Citação ≠ relação</li>
          <li>Investigação ≠ culpa</li>
          <li>Contato político ≠ relação criminosa</li>
          <li>Conexão potencial aparece só com status explícito (não como fato)</li>
          <li>Expandir com operações, território e fluxos só com fonte nível 1/2</li>
        </ul>
        <p className="faint">
          Spec: <code>adição funcionaidades.md</code> · Fontes:{" "}
          <Link href="/fontes">/fontes</Link> ·{" "}
          <Link href="/investigar">Investigar</Link>
        </p>
      </section>
    </div>
  );
}
