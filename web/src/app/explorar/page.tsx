import Link from "next/link";
import EvidenceDrawer, { type EvidenceItem } from "@/components/EvidenceDrawer";

type Named = {
  id: string;
  nome?: string;
  titulo?: string;
  partido?: string | null;
  cargo_atual?: string | null;
  orgao?: string;
  tipo?: string;
};

function apiBase(): string {
  return (
    process.env.ATLAS_API_URL ||
    process.env.NEXT_PUBLIC_ATLAS_API_URL ||
    "http://localhost:8001"
  ).replace(/\/$/, "");
}

async function buscaKb(q: string) {
  try {
    const res = await fetch(
      `${apiBase()}/v1/busca?q=${encodeURIComponent(q)}`,
      { next: { revalidate: 30 } }
    );
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function buscaOs(q: string) {
  try {
    const res = await fetch(
      `${apiBase()}/v1/busca/opensearch?q=${encodeURIComponent(q)}&size=24`,
      { next: { revalidate: 30 } }
    );
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export default async function ExplorarPage({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const q = searchParams.q || "";
  const [kb, os] = q.trim()
    ? await Promise.all([buscaKb(q), buscaOs(q)])
    : [null, null];

  const evidence: EvidenceItem[] = (os?.evidence || []) as EvidenceItem[];
  const sourceParts = [
    kb ? "api/kb" : null,
    os?.opensearch ? "opensearch" : os ? "opensearch_degraded" : null,
  ].filter(Boolean);

  const sections: {
    title: string;
    items: Named[];
    href: (id: string) => string;
  }[] = [
    {
      title: "Pessoas",
      items: (kb?.pessoas || []) as Named[],
      href: (id) => `/pessoas/${id}`,
    },
    {
      title: "Empresas",
      items: (kb?.empresas || []) as Named[],
      href: (id) => `/empresas/${id}`,
    },
    {
      title: "Partidos",
      items: (kb?.partidos || []) as Named[],
      href: (id) => `/partidos/${id}`,
    },
    {
      title: "Instituições",
      items: (kb?.instituicoes || []) as Named[],
      href: (id) => `/instituicoes/${id}`,
    },
    {
      title: "Casos",
      items: (kb?.casos || []) as Named[],
      href: (id) => `/casos/${id}`,
    },
    {
      title: "Documentos (OpenSearch)",
      items: ((os?.hits || []) as Named[]).map((d) => ({
        ...d,
        id: d.id,
        nome: d.titulo || d.nome || d.id,
      })),
      href: (id) =>
        id.startsWith("ent_")
          ? `/pessoas/${id.replace(/^ent_/, "")}`
          : `/fontes/${id}`,
    },
  ];

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Explorar</h1>
        <p className="muted">
          Busca híbrida: entidades via API + documentos OpenSearch-first.
        </p>
        <p className="faint">Fonte: {sourceParts.join(" + ") || "—"}</p>
      </div>
      <form className="filters" method="get">
        <input
          name="q"
          defaultValue={q}
          placeholder="Nome, partido, documento…"
          id="atlas-global-search"
        />
        <button className="btn" type="submit">
          Buscar
        </button>
      </form>
      {!q.trim() ? (
        <p className="muted">Digite um termo para buscar.</p>
      ) : (
        <>
          <EvidenceDrawer items={evidence} title="Evidências / documentos" />
          {sections.map((s) =>
            s.items.length ? (
              <section key={s.title} className="stack">
                <h2 className="section-title" style={{ fontSize: "1.1rem" }}>
                  {s.title} ({s.items.length})
                </h2>
                <div className="list-block">
                  {s.items.slice(0, 40).map((item) => (
                    <Link
                      key={item.id}
                      href={s.href(item.id)}
                      className="list-item"
                    >
                      <span className="item-title">
                        {item.nome || item.titulo || item.id}
                      </span>
                      <span className="item-meta">
                        {[item.partido, item.cargo_atual, item.orgao]
                          .filter(Boolean)
                          .join(" · ") || item.id}
                      </span>
                    </Link>
                  ))}
                </div>
              </section>
            ) : null
          )}
          {sections.every((s) => !s.items.length) ? (
            <p className="muted">Nenhum resultado para “{q}”.</p>
          ) : null}
        </>
      )}
    </div>
  );
}
