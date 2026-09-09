"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Health = {
  ok?: boolean;
  api?: string;
  fase?: number;
  region?: string;
  superficie?: string;
  mobile?: string;
  postgres?: boolean;
  redis?: boolean;
  opensearch?: boolean;
  embeddings?: boolean;
  embeddings_dense?: boolean;
  neo4j_env?: boolean;
  kafka_bootstrap?: string | null;
  observabilidade?: {
    metrics?: string;
    prometheus?: string;
    grafana?: string;
  };
  kb?: string;
};

type CoverageSource = {
  source_id: string;
  source_name?: string;
  status?: string;
  priority?: number | string;
  last_ingested_at?: string | null;
  last_run_ok?: boolean;
  counts?: Record<string, number | string>;
};

type Coverage = {
  live?: {
    total_sources?: number;
    por_status?: Record<string, number>;
    sources?: CoverageSource[];
    gerado_em?: string;
  };
};

function Dot({ ok }: { ok?: boolean }) {
  return (
    <span
      aria-hidden
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: 999,
        marginRight: 8,
        background: ok ? "#2f6f4e" : "#8a3b2e",
      }}
    />
  );
}

function statusTone(status?: string) {
  const s = (status || "").toLowerCase();
  if (s === "active") return "#2f6f4e";
  if (s === "partial" || s === "stub") return "#9a7b2f";
  return "#6b6b6b";
}

export default function StatusPage() {
  const api = process.env.NEXT_PUBLIC_ATLAS_API || "http://127.0.0.1:8000";
  const [h, setH] = useState<Health | null>(null);
  const [cov, setCov] = useState<Coverage | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [rs, rc] = await Promise.all([
          fetch(`${api}/v1/status`),
          fetch(`${api}/v1/fontes/coverage`),
        ]);
        if (!rs.ok) throw new Error(String(rs.status));
        const j = await rs.json();
        if (!cancelled) setH(j);
        if (rc.ok) {
          const c = await rc.json();
          if (!cancelled) setCov(c);
        }
      } catch {
        if (!cancelled) setErr("API indisponível — tente :8000 ou :8001");
      }
    }
    load();
    const t = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [api]);

  const sources = cov?.live?.sources || [];

  return (
    <main className="page-pad">
      <p className="eyebrow">
        <Link href="/">ATLAS</Link> · Fase 4
      </p>
      <h1 className="section-title">Status operacional</h1>
      <p className="lede">
        Superfície web. Cobertura das fontes oficiais (SOURCE_REGISTRY) e stack.
      </p>

      {err && <p className="muted">{err}</p>}

      {h && (
        <>
          <p className="faint" style={{ marginTop: "1rem" }}>
            API {h.api} · fase {h.fase} · região {h.region} · KB {h.kb}
          </p>
          <ul className="plain-list" style={{ marginTop: "1.25rem" }}>
            <li>
              <Dot ok={h.postgres} />
              PostgreSQL
            </li>
            <li>
              <Dot ok={h.redis} />
              Redis
            </li>
            <li>
              <Dot ok={h.opensearch} />
              OpenSearch
            </li>
            <li>
              <Dot ok={h.neo4j_env} />
              Neo4j (env)
            </li>
            <li>
              <Dot ok={!!h.kafka_bootstrap} />
              Kafka bootstrap {h.kafka_bootstrap || "—"}
            </li>
            <li>
              <Dot ok={h.embeddings} />
              Embeddings TF-IDF
            </li>
            <li>
              <Dot ok={h.embeddings_dense} />
              Embeddings densos 384-d
            </li>
            <li>
              <Dot ok={h.mobile === "adiado"} />
              Mobile: {h.mobile || "adiado"}
            </li>
          </ul>

          <section style={{ marginTop: "2rem" }}>
            <h2 className="section-title" style={{ fontSize: "1.2rem" }}>
              Fontes — cobertura
            </h2>
            <p className="muted" style={{ marginBottom: "0.75rem" }}>
              {cov?.live?.total_sources ?? "—"} fontes no registry
              {cov?.live?.por_status
                ? ` · ${Object.entries(cov.live.por_status)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(", ")}`
                : ""}
              {" · "}
              <Link href="/fontes">documentos KB</Link>
              {" · "}
              <a href={`${api}/v1/fontes/registry`} target="_blank" rel="noreferrer">
                /v1/fontes/registry
              </a>
            </p>
            {sources.length > 0 && (
              <div style={{ overflowX: "auto" }}>
                <table className="data-table" style={{ width: "100%", fontSize: "0.9rem" }}>
                  <thead>
                    <tr>
                      <th align="left">Fonte</th>
                      <th align="left">Status</th>
                      <th align="left">Última ingestão</th>
                      <th align="left">Contagens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((s) => (
                      <tr key={s.source_id}>
                        <td>
                          <code>{s.source_id}</code>
                          {s.source_name ? (
                            <span className="faint"> — {s.source_name}</span>
                          ) : null}
                        </td>
                        <td>
                          <span style={{ color: statusTone(s.status) }}>
                            {s.status || "—"}
                          </span>
                          {s.last_run_ok === false ? " · falha" : ""}
                        </td>
                        <td className="faint">
                          {s.last_ingested_at
                            ? new Date(s.last_ingested_at).toLocaleString("pt-BR")
                            : "nunca"}
                        </td>
                        <td className="faint">
                          {s.counts && Object.keys(s.counts).length
                            ? Object.entries(s.counts)
                                .map(([k, v]) => `${k}=${v}`)
                                .join(" · ")
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section style={{ marginTop: "2rem" }}>
            <h2 className="section-title" style={{ fontSize: "1.2rem" }}>
              Observabilidade
            </h2>
            <ul className="plain-list">
              <li>
                <a href={`${api}/metrics`} target="_blank" rel="noreferrer">
                  /metrics
                </a>
              </li>
              <li>
                <a
                  href={h.observabilidade?.prometheus || "http://localhost:9090"}
                  target="_blank"
                  rel="noreferrer"
                >
                  Prometheus :9090
                </a>
              </li>
              <li>
                <a
                  href={h.observabilidade?.grafana || "http://localhost:3002"}
                  target="_blank"
                  rel="noreferrer"
                >
                  Grafana :3002
                </a>{" "}
                <span className="faint">(atlas / atlasbrasil)</span>
              </li>
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
