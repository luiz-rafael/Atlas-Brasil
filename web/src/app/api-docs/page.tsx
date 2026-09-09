import Link from "next/link";

export default function ApiDocsPage() {
  const base = process.env.NEXT_PUBLIC_ATLAS_API || "http://localhost:8000";
  const routes = [
    "/health",
    "/v1/meta",
    "/v1/contas/resumo?year=2024",
    "/v1/contas/divida?year=2024",
    "/v1/contas/resultado-fiscal?year=2024",
    "/v1/contas/renuncias?year=2024",
    "/v1/contas/pessoal?year=2024",
    "/v1/contas/cno?limit=20",
    "/v1/busca?q=Lula",
    "/v1/grafo?centro_id=p_lula&profundidade=2",
    "/v1/grafo/caminho?a=p_lula&b=p_jair",
    "/v1/grafo/encontros?a=p_lula&b=p_jair",
    "/v1/grafo/hubs?metric=degree",
    "/v1/grafo/comunidades",
    "/v1/grafo/comparar?a=p_lula&b=p_jair",
    "/v1/timeline",
    "/v1/timeline/como-chegamos?evento_id=",
    "/v1/fontes",
    "/v1/indicadores/meta",
    "/v1/indicadores/observations",
    "/v1/indicadores/choropleth",
    "/v1/financeiro",
    "/v1/poder/2026",
  ];

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">API ATLAS BRASIL</h1>
        <p className="muted">
          FastAPI em <code>{base}</code> — mesma API para site e futuro app.
        </p>
      </div>
      <div className="list-block">
        {routes.map((r) => (
          <a
            key={r}
            className="list-item"
            href={`${base}${r}`}
            target="_blank"
            rel="noreferrer"
          >
            <span className="item-title">{r}</span>
          </a>
        ))}
      </div>
      <p className="faint">
        Docs interativos:{" "}
        <a href={`${base}/docs`} target="_blank" rel="noreferrer">
          {base}/docs
        </a>
        {" · "}
        <Link href="/metodologia">Metodologia</Link>
      </p>
    </div>
  );
}
