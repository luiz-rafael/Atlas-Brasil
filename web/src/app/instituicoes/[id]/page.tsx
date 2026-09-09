import { notFound } from "next/navigation";
import { entityById, relacoesDe, labelOf } from "@/lib/kb";
import Link from "next/link";

export default function InstituicaoPage({
  params,
}: {
  params: { id: string };
}) {
  const inst = entityById(params.id);
  if (!inst || (inst.tipo !== "instituicao" && inst.tipo !== "conceito"))
    notFound();
  const rels = relacoesDe(inst.id);

  return (
    <div className="page stack">
      <div>
        <p className="faint">{inst.tipo === "conceito" ? "Conceito" : "Instituição"}</p>
        <h1 className="section-title">{inst.nome}</h1>
      </div>
      {inst.id === "conceito_centrao" ? (
        <p className="prose-note">
          Centrão é fenômeno político de coalizão/fisiologia. Não equivale a
          organização criminosa. Analisar pessoas e fatos individualmente.
        </p>
      ) : null}
      <section className="list-block">
        {rels.map((r) => {
          const other = r.origem === inst.id ? r.destino : r.origem;
          return (
            <div key={r.id} className="list-item">
              <p className="item-title">
                {r.tipo} ·{" "}
                <Link href={`/pessoas/${other}`}>{labelOf(other)}</Link>
              </p>
              <p className="faint">{r.justificativa_documental}</p>
            </div>
          );
        })}
      </section>
    </div>
  );
}
