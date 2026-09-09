import Link from "next/link";
import {
  hubsByPeriod,
  hubsRanking,
  METRIC_DISCLAIMER,
  type MetricName,
} from "@/lib/network-metrics";

const METRICS: { value: MetricName; label: string }[] = [
  { value: "degree", label: "Degree (conexões)" },
  { value: "betweenness", label: "Betweenness (pontes)" },
  { value: "closeness", label: "Closeness" },
  { value: "eigenvector", label: "Eigenvector" },
];

const TIPOS = [
  { value: "todos", label: "Todos" },
  { value: "pessoa", label: "Pessoas" },
  { value: "empresa", label: "Empresas" },
  { value: "partido", label: "Partidos" },
  { value: "instituicao", label: "Instituições" },
  { value: "caso", label: "Casos" },
];

export default function HubsPage({
  searchParams,
}: {
  searchParams: {
    metric?: string;
    tipo?: string;
    de?: string;
    ate?: string;
    por_periodo?: string;
  };
}) {
  const metric = (searchParams.metric || "degree") as MetricName;
  const tipo = searchParams.tipo || "todos";
  const de = searchParams.de;
  const ate = searchParams.ate;
  const porPeriodo = searchParams.por_periodo === "1";

  const ranking = hubsRanking(metric, {
    tipo,
    de,
    ate,
    limit: 30,
  });
  const periodos = porPeriodo ? hubsByPeriod(metric) : null;

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Hubs da rede</h1>
        <p className="muted">
          Ranking por centralidade estrutural — descoberto pelos dados, não
          pré-escolhido.
        </p>
      </div>

      <form className="filters" method="get">
        <select name="metric" defaultValue={metric}>
          {METRICS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
        <select name="tipo" defaultValue={tipo}>
          {TIPOS.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <input name="de" defaultValue={de || ""} placeholder="De (ano)" />
        <input name="ate" defaultValue={ate || ""} placeholder="Até (ano)" />
        <label className="faint" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input
            type="checkbox"
            name="por_periodo"
            value="1"
            defaultChecked={porPeriodo}
          />
          Por período
        </label>
        <button className="btn" type="submit">
          Calcular
        </button>
      </form>

      <p className="prose-note">{METRIC_DISCLAIMER}</p>

      {periodos ? (
        periodos.periodos.map((p) => (
          <section key={p.label} className="list-block">
            <h2 className="section-title" style={{ fontSize: "1.1rem" }}>
              {p.label}
            </h2>
            {p.hubs.length === 0 ? (
              <p className="muted">Sem arestas neste intervalo.</p>
            ) : (
              p.hubs.map((h) => (
                <Link
                  key={h.id}
                  href={`/grafo?centro=${h.id}&profundidade=1`}
                  className="list-item"
                >
                  <span className="item-title">
                    #{h.rank} {h.nome}
                  </span>
                  <span className="item-meta">
                    {h.tipo} · score {h.score}
                  </span>
                </Link>
              ))
            )}
          </section>
        ))
      ) : (
        <div className="list-block">
          {ranking.ranking.map((h) => (
            <Link
              key={h.id}
              href={`/grafo?centro=${h.id}&profundidade=1`}
              className="list-item"
            >
              <span className="item-title">
                #{h.rank} {h.nome}
              </span>
              <span className="item-meta">
                {h.tipo} · {metric}={h.score} · raw={h.raw}
              </span>
            </Link>
          ))}
        </div>
      )}

      <p className="faint">
        <Link href="/grafo/comunidades">Comunidades e pontes</Link>
        {" · "}
        <Link href="/grafo">Grafo</Link>
      </p>
    </div>
  );
}
