import Link from "next/link";

function apiBase(): string {
  return (
    process.env.ATLAS_API_URL ||
    process.env.NEXT_PUBLIC_ATLAS_API_URL ||
    "http://localhost:8001"
  ).replace(/\/$/, "");
}

async function fetchMagList(q?: string) {
  try {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    p.set("limit", "100");
    const res = await fetch(`${apiBase()}/v1/magistrados?${p}`, {
      next: { revalidate: 120 },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export default async function MagistradosPage({
  searchParams,
}: {
  searchParams?: { q?: string };
}) {
  const data = await fetchMagList(searchParams?.q);
  const items = data?.items || [];

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Magistrados</h1>
        <p className="muted">
          Remuneração pública (CNJ) — transparência de pessoal.
        </p>
        <p className="prose-note">
          {data?.disclaimer ||
            "Remuneração ≠ culpa. gross_total ≠ subsídio. null ≠ zero."}
        </p>
        <p className="faint">Fonte: {data?.source || "—"} · total {data?.total ?? 0}</p>
      </div>
      <form className="filters" method="get">
        <input
          name="q"
          defaultValue={searchParams?.q || ""}
          placeholder="Nome…"
        />
        <button className="btn" type="submit">
          Filtrar
        </button>
      </form>
      <div className="list-block">
        {items.map(
          (m: {
            magistrate_id: string;
            display_name?: string;
            normalized_name?: string;
            court_id?: string;
            position?: string;
          }) => (
            <Link
              key={m.magistrate_id}
              href={`/magistrados/${m.magistrate_id}`}
              className="list-item"
            >
              <span className="item-title">
                {m.display_name || m.normalized_name || m.magistrate_id}
              </span>
              <span className="item-meta">
                {[m.court_id, m.position].filter(Boolean).join(" · ")}
              </span>
            </Link>
          )
        )}
      </div>
      {!items.length ? (
        <p className="muted">
          Sem magistrados no serving. Rode{" "}
          <code>python -u pipelines/ops/load_magistrates.py</code>.
        </p>
      ) : null}
    </div>
  );
}
