import Link from "next/link";
import { fetchEmpresasList } from "@/lib/empresas";
import { getKB } from "@/lib/kb";

export default async function EmpresasPage({
  searchParams,
}: {
  searchParams?: { q?: string };
}) {
  const api = await fetchEmpresasList({ q: searchParams?.q, limit: 500 });
  let items =
    api?.items.map((e) => ({
      id: e.company_id,
      nome: e.razao_social || e.nome_fantasia || e.company_id,
      meta: [e.cnpj, e.uf].filter(Boolean).join(" · ") || "empresa",
    })) || [];
  let source = api?.source || "api";

  if (!api) {
    items = getKB()
      .entidades.filter((e) => e.tipo === "empresa")
      .map((e) => ({
        id: e.id,
        nome: e.nome,
        meta: (e.tags || []).join(", ") || "empresa",
      }));
    source = "kb_fallback";
  }

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Empresas</h1>
        <p className="muted">
          Empresas e grupos com relação documental a política pública,
          contratos, financiamento ou investigações.
        </p>
        <p className="faint">Fonte: {source}</p>
      </div>
      <form className="filters" method="get">
        <input
          name="q"
          defaultValue={searchParams?.q || ""}
          placeholder="Filtrar por razão social / CNPJ..."
        />
        <button className="btn" type="submit">
          Filtrar
        </button>
      </form>
      <div className="list-block">
        {items.map((e) => (
          <Link key={e.id} href={`/empresas/${e.id}`} className="list-item">
            <span className="item-title">{e.nome}</span>
            <span className="item-meta">{e.meta}</span>
          </Link>
        ))}
      </div>
      {!items.length ? (
        <p className="muted">Nenhuma empresa neste filtro.</p>
      ) : null}
    </div>
  );
}
