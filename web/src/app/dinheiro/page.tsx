import Link from "next/link";
import { fetchDinheiroResumo, fetchDinheiroTab } from "@/lib/dinheiro";
import { formatBRL, formatReaisExact } from "@/lib/format";

const TABS: { id: string; label: string }[] = [
  { id: "contratos", label: "Contratos PNCP" },
  { id: "licitacoes", label: "Licitações" },
  { id: "emendas", label: "Emendas" },
  { id: "transferencias", label: "Transferências" },
  { id: "sancoes", label: "Sanções" },
  { id: "empresas", label: "Empresas" },
  { id: "fluxos", label: "Fluxos" },
  { id: "caminhos", label: "Cruzamentos" },
];

export default async function DinheiroPage({
  searchParams,
}: {
  searchParams: { caso_id?: string; tab?: string; q?: string; uf?: string };
}) {
  const tab = searchParams.tab || "contratos";
  const q = (searchParams.q || "").trim();
  const uf = (searchParams.uf || "").trim().toUpperCase();
  const resumo = await fetchDinheiroResumo();
  const data = await fetchDinheiroTab(tab, {
    caso_id: searchParams.caso_id,
    q: q || undefined,
    uf: uf || undefined,
    limit: 120,
  });

  const counts = data?.counts || resumo?.counts || {};
  const items = data?.items || [];

  function tabHref(id: string) {
    const p = new URLSearchParams();
    p.set("tab", id);
    if (searchParams.caso_id) p.set("caso_id", searchParams.caso_id);
    if (q) p.set("q", q);
    if (uf) p.set("uf", uf);
    return `/dinheiro?${p.toString()}`;
  }

  return (
    <div className="page stack atlas-dinheiro">
      <div>
        <h1 className="section-title">Dinheiro</h1>
        <p className="muted">
          Ranking por valor (mi / bi). Contrato ≠ emenda ≠ transferência ≠
          sanção. Contas do Brasil (resultado/dívida/carga) em{" "}
          <Link href="/contas">/contas</Link>.
        </p>
        <p className="prose-note">
          {data?.disclaimer ||
            resumo?.disclaimer ||
            "Nunca classificamos automaticamente uma transferência, emenda ou contrato como ilegal."}
        </p>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={tabHref(t.id)}
            className={tab === t.id ? "active" : undefined}
          >
            {t.label}
            {counts[t.id] != null ? ` (${counts[t.id]})` : ""}
          </Link>
        ))}
        <Link href="/contas?tab=carga">Carga tributária →</Link>
      </div>

      <form className="filters atlas-money-filters" method="get">
        <input type="hidden" name="tab" value={tab} />
        {searchParams.caso_id ? (
          <input type="hidden" name="caso_id" value={searchParams.caso_id} />
        ) : null}
        <input
          name="q"
          defaultValue={q}
          placeholder="Filtrar nome / CNPJ / órgão…"
        />
        <input
          name="uf"
          defaultValue={uf}
          placeholder="UF"
          maxLength={2}
          style={{ width: 64, textTransform: "uppercase" }}
        />
        <button className="btn" type="submit">
          Filtrar
        </button>
      </form>

      {!data ? (
        <p className="muted">
          API de dinheiro indisponível. Suba a API em :8001.
        </p>
      ) : (
        <div className="list-block">
          {items.map((e, i) => {
            const id = String(e.id || i);
            const nome = String(e.nome || id);
            const valor = e.valor as number | undefined;
            const href =
              e.tipo === "empresa" || String(id).startsWith("e_")
                ? `/empresas/${id}`
                : tab === "empresas"
                  ? `/empresas/${id}`
                  : `/grafo?centro=${encodeURIComponent(id)}`;
            return (
              <Link
                key={id}
                href={href}
                className="list-item atlas-rank-row"
              >
                <span className="atlas-rank-pos">#{i + 1}</span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span className="item-title">{nome}</span>
                  <span
                    className="item-meta"
                    title={
                      valor != null ? formatReaisExact(Number(valor)) : undefined
                    }
                  >
                    {[
                      e.tipo ? String(e.tipo) : null,
                      e.uf ? String(e.uf) : null,
                      valor != null ? formatBRL(Number(valor)) : null,
                      e.cnpj ? `CNPJ ${e.cnpj}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
              </Link>
            );
          })}
          {!items.length ? (
            <p className="muted">Nenhum item nesta categoria/filtro.</p>
          ) : (
            <p className="item-meta muted">
              Ranking por valor · {items.length}
              {typeof data.total === "number" ? ` de ${data.total}` : ""} itens
              {uf ? ` · UF ${uf}` : ""}
              {q ? ` · filtro “${q}”` : ""}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
