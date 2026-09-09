"use client";

import { useState } from "react";
import Link from "next/link";

type ErHit = {
  entity_id: string;
  nome: string;
  tipo?: string;
  score: number;
  method?: string;
  mention?: string;
};

type SemHit = { doc_id: string; titulo?: string; score: number };

export default function NlpPage() {
  const api = process.env.NEXT_PUBLIC_ATLAS_API || "http://127.0.0.1:8000";
  const [q, setQ] = useState("Lula e o STF na Lava Jato");
  const [er, setEr] = useState<ErHit[]>([]);
  const [sem, setSem] = useState<SemHit[]>([]);
  const [modelo, setModelo] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      const [r1, r2] = await Promise.all([
        fetch(`${api}/v1/nlp/resolve?q=${encodeURIComponent(q)}`),
        fetch(`${api}/v1/busca/semantica?q=${encodeURIComponent(q)}&size=8`),
      ]);
      if (!r1.ok || !r2.ok) throw new Error("API");
      const j1 = await r1.json();
      const j2 = await r2.json();
      setEr(j1.entidades || []);
      setSem(j2.hits || []);
      setModelo(j2.modelo || "");
    } catch {
      setErr("API indisponível. Suba a FastAPI (:8000) e rode os jobs NLP da Fase 3.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-pad">
      <p className="eyebrow">
        <Link href="/">ATLAS</Link> · Fase 3
      </p>
      <h1 className="section-title">NLP · Entity resolution + semântica</h1>
      <p className="lede">
        Candidatos de entidade e documentos próximos por embedding. Não cria
        arestas sozinho — revisão humana.
      </p>

      <form onSubmit={run} className="stack-gap" style={{ marginTop: "1.5rem" }}>
        <label className="faint">Texto / pergunta</label>
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          rows={3}
          className="input-block"
          style={{ width: "100%" }}
        />
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? "Processando…" : "Resolver + buscar"}
        </button>
      </form>

      {err && <p className="muted" style={{ marginTop: "1rem" }}>{err}</p>}

      <section style={{ marginTop: "2rem" }}>
        <h2 className="section-title" style={{ fontSize: "1.25rem" }}>
          Entidades candidatas
        </h2>
        {er.length === 0 ? (
          <p className="faint">Nenhuma ainda.</p>
        ) : (
          <ul className="plain-list">
            {er.map((h) => (
              <li key={`${h.entity_id}-${h.mention || h.score}`}>
                <Link href={`/explorar?q=${encodeURIComponent(h.nome)}`}>
                  {h.nome}
                </Link>
                <span className="faint">
                  {" "}
                  · {h.tipo || "?"} · score {h.score} · {h.method}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginTop: "2rem" }}>
        <h2 className="section-title" style={{ fontSize: "1.25rem" }}>
          Vizinhos semânticos {modelo ? `(${modelo})` : ""}
        </h2>
        {sem.length === 0 ? (
          <p className="faint">
            Sem embeddings. Rode{" "}
            <code>python pipelines/embeddings/build_embeddings.py</code>
          </p>
        ) : (
          <ul className="plain-list">
            {sem.map((h) => (
              <li key={h.doc_id}>
                {h.titulo || h.doc_id}
                <span className="faint"> · {h.score}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="faint" style={{ marginTop: "2rem" }}>
        Também: <Link href="/ia">GraphRAG</Link> ·{" "}
        <Link href="/grafo/comunidades">Comunidades / GDS-lite</Link>
      </p>
    </main>
  );
}
