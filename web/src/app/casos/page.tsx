import Link from "next/link";
import { fetchCasosList } from "@/lib/casos";
import { getKB } from "@/lib/kb";

export default async function CasosPage({
  searchParams,
}: {
  searchParams?: { q?: string };
}) {
  const api = await fetchCasosList({ q: searchParams?.q, limit: 500 });
  let casos = api?.items || [];
  let source = api?.source || "api";

  if (!api) {
    casos = (getKB().casos || []).map((c) => ({
      id: c.id,
      nome: c.nome,
      periodo: c.periodo,
      eixos: c.eixos,
    }));
    source = "kb_fallback";
  }

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Casos</h1>
        <p className="muted">
          Dossiês de investigações e escândalos com status jurídico separado.
          Processo ≠ culpa.
        </p>
        <p className="faint">Fonte: {source}</p>
        <p className="faint" style={{ marginTop: "0.75rem" }}>
          <Link href="/investigacoes-beta">Lava Jato — INQ 3989</Link>
        </p>
      </div>
      <form className="filters" method="get">
        <input
          name="q"
          defaultValue={searchParams?.q || ""}
          placeholder="Filtrar por nome..."
        />
        <button className="btn" type="submit">
          Filtrar
        </button>
      </form>
      <div className="list-block">
        {casos.map((c) => (
          <Link key={c.id} href={`/casos/${c.id}`} className="list-item">
            <span className="item-title">{c.nome}</span>
            <span className="item-meta">
              {c.periodo || "—"}
              {c.eixos?.length ? ` · ${c.eixos.join(", ")}` : ""}
            </span>
          </Link>
        ))}
      </div>
      {!casos.length ? (
        <p className="muted">Nenhum caso editorial neste filtro.</p>
      ) : null}
    </div>
  );
}
