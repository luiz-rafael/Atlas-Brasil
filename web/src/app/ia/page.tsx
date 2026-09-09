"use client";

import { useState } from "react";
import Link from "next/link";

type IaResponse = {
  pergunta: string;
  resposta: string;
  modo: string;
  disclaimer: string;
  evidencias?: {
    entidades_detectadas?: string[];
    documentos?: Array<{ titulo?: string; url?: string; orgao?: string }>;
  };
};

export default function IaPage() {
  const [q, setQ] = useState(
    "Qual o caminho documental entre Lula e Bolsonaro?"
  );
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<IaResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    const api = process.env.NEXT_PUBLIC_ATLAS_API || "http://127.0.0.1:8000";
    try {
      const res = await fetch(`${api}/v1/ia/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pergunta: q }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (ex) {
      setErr(
        "API indisponível. Suba a FastAPI (:8000) e OpenSearch se quiser busca completa."
      );
      setData(null);
      void ex;
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">GraphRAG · ATLAS IA</h1>
        <p className="muted">
          Pergunta → grafo + documentos (+ OpenSearch) → resposta com evidências.
          Sem acusação automática.
        </p>
      </div>

      <form className="stack" onSubmit={ask}>
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          rows={3}
          style={{
            width: "100%",
            background: "var(--bg-elevated)",
            border: "1px solid var(--line)",
            color: "var(--ink)",
            padding: "0.75rem",
            borderRadius: 4,
            font: "inherit",
          }}
        />
        <button className="btn" type="submit" disabled={loading}>
          {loading ? "Consultando…" : "Perguntar"}
        </button>
      </form>

      {err ? <p className="prose-note">{err}</p> : null}

      {data ? (
        <section className="stack">
          <p className="faint">Modo: {data.modo}</p>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              background: "var(--bg-elevated)",
              border: "1px solid var(--line)",
              padding: "1rem",
              borderRadius: 4,
              fontFamily: "var(--font-body), sans-serif",
              lineHeight: 1.6,
            }}
          >
            {data.resposta}
          </pre>
          {data.evidencias?.entidades_detectadas?.length ? (
            <p className="muted">
              Entidades: {data.evidencias.entidades_detectadas.join(" · ")}
            </p>
          ) : null}
          {data.evidencias?.documentos?.length ? (
            <div className="list-block">
              <h2 className="section-title" style={{ fontSize: "1.1rem" }}>
                Fontes usadas
              </h2>
              {data.evidencias.documentos.map((d, i) => (
                <div key={i} className="list-item">
                  <p className="item-title">{d.titulo}</p>
                  <p className="item-meta">{d.orgao}</p>
                  {d.url ? (
                    <p className="faint">
                      <a href={d.url} target="_blank" rel="noreferrer">
                        Abrir
                      </a>
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          <p className="prose-note">{data.disclaimer}</p>
        </section>
      ) : null}

      <p className="faint">
        <Link href="/explorar">Explorar</Link>
        {" · "}
        <Link href="/grafo">Grafo</Link>
        {" · "}
        <Link href="/api-docs">API</Link>
      </p>
    </div>
  );
}
