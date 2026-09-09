import { Suspense } from "react";
import Link from "next/link";
import InvestigationTrail from "@/components/InvestigationTrail";
import { getKB } from "@/lib/kb";
import { PATH_DISCLAIMER } from "@/lib/graph-engine";

export default function InvestigarPage() {
  const kb = getKB();
  const suggestions = [
    ...kb.entidades
      .filter((e) => !e.isolada)
      .slice(0, 40)
      .map((e) => ({ id: e.id, label: e.nome })),
    ...kb.casos.map((c) => ({ id: c.id, label: c.nome })),
  ];

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Investigar</h1>
        <p className="muted">
          Monte uma trilha documental e compartilhe o link. O Atlas documenta —
          não acusa.
        </p>
      </div>

      <p className="prose-note">{PATH_DISCLAIMER}</p>

      <Suspense fallback={<p className="muted">Carregando trilha…</p>}>
        <InvestigationTrail suggestions={suggestions} />
      </Suspense>

      <section className="stack">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Camadas (obrigatório em temas sensíveis)
        </h2>
        <ul className="muted" style={{ lineHeight: 1.7, paddingLeft: "1.2rem" }}>
          <li>O que sabemos (fato documentado)</li>
          <li>O que foi alegado / investigado</li>
          <li>O que foi decidido (condenação, absolvição, anulação…)</li>
          <li>O que continua desconhecido</li>
        </ul>
      </section>

      <p className="faint">
        <Link href="/grafo/conexao">Encontrar conexão</Link>
        {" · "}
        <Link href="/grafo/encontros">Pontos de encontro</Link>
        {" · "}
        <Link href="/fontes">Fontes</Link>
      </p>
    </div>
  );
}
