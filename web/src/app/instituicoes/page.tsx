import Link from "next/link";
import { getKB } from "@/lib/kb";

export default function InstituicoesPage() {
  const kb = getKB();
  const list = kb.entidades.filter((e) => e.tipo === "instituicao");

  return (
    <div className="stack">
      <div>
        <p className="eyebrow">Catálogo</p>
        <h1 className="section-title">Instituições</h1>
        <p className="muted">{list.length} entidades no corte atual.</p>
      </div>
      <div className="list-block">
        {list.map((e) => (
          <Link key={e.id} href={`/instituicoes/${e.id}`} className="doc-card">
            <span className="stripe oficial" />
            <span>
              <strong>{e.nome}</strong>
              <p className="faint" style={{ margin: "0.25rem 0 0" }}>
                {(e.tags || []).join(" · ")}
              </p>
            </span>
            <span className="faint">Abrir →</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
