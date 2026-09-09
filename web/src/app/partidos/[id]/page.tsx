import Link from "next/link";
import { notFound } from "next/navigation";
import { entityById, labelOf, pessoas, relacoesDe } from "@/lib/kb";

export default function PartidoPage({ params }: { params: { id: string } }) {
  const partido = entityById(params.id);
  if (!partido || partido.tipo !== "partido") notFound();
  const membros = pessoas({}).filter(
    (p) =>
      (p.partido || "").toLowerCase() === partido.nome.toLowerCase() ||
      relacoesDe(p.id).some(
        (r) =>
          (r.destino === partido.id || r.origem === partido.id) &&
          ["membro_mesmo_partido", "lider"].includes(r.tipo)
      )
  );
  const rels = relacoesDe(partido.id);

  return (
    <div className="page stack">
      <div>
        <p className="faint">Partido</p>
        <h1 className="section-title">{partido.nome}</h1>
      </div>
      <section className="list-block">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Pessoas relacionadas
        </h2>
        {membros.map((p) => (
          <Link key={p.id} href={`/pessoas/${p.id}`} className="list-item">
            <span className="item-title">{p.nome}</span>
            <span className="item-meta">{p.cargo_atual}</span>
          </Link>
        ))}
        {rels.map((r) => {
          const other = r.origem === partido.id ? r.destino : r.origem;
          return (
            <div key={r.id} className="list-item">
              <p className="item-title">
                {r.tipo}: {labelOf(other)}
              </p>
            </div>
          );
        })}
      </section>
    </div>
  );
}
