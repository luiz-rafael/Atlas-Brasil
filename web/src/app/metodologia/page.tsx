import Link from "next/link";
import { getKB } from "@/lib/kb";

export default function MetodologiaPage() {
  const poder = getKB().mapa_poder_2026;
  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">Metodologia</h1>
        <p className="muted">
          ATLAS BRASIL não produz veredito moral. Oferece base documental
          navegável.
        </p>
      </div>

      <section className="stack">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Princípio fundamental
        </h2>
        <ul className="muted" style={{ lineHeight: 1.7, paddingLeft: "1.2rem" }}>
          <li>Investigação ≠ prova de culpa</li>
          <li>Acusação ≠ condenação</li>
          <li>Relação política ≠ corrupção</li>
          <li>Doação legal ≠ propina</li>
          <li>Nomeação ≠ favorecimento ilícito</li>
          <li>Arquivamento ≠ inocência absoluta</li>
          <li>Centrão ≠ organização criminosa</li>
        </ul>
      </section>

      <section className="stack">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Camadas
        </h2>
        <p className="muted">
          Fato documentado → investigação → acusação → réu → condenação /
          absolvição / arquivamento / prescrição / anulação → hipótese.
        </p>
      </section>

      <section className="stack">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Análise de redes
        </h2>
        <p className="muted">
          Centralidade é medida estrutural — não equivale a poder ou culpa.{" "}
          <Link href="/grafo/hubs">Hubs</Link>
          {" · "}
          <Link href="/grafo/comunidades">Comunidades</Link>
        </p>
      </section>

      <section className="stack">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Fontes
        </h2>
        <p className="muted">
          Nível 1 primária (STF, DOU, PF, MP, TCU) · Nível 2 jornalismo
          profissional · Nível 3 acadêmica · Nível 4 outras (baixa
          confiabilidade).
        </p>
        <p className="faint">
          <Link href="/fontes">Abrir central de fontes</Link>
          {" · "}
          <Link href="/dinheiro">Mapa de dinheiro</Link>
        </p>
      </section>

      <section className="stack">
        <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
          Regra de ouro do grafo
        </h2>
        <p className="prose-note">
          Nenhuma relação aparece sem justificativa documental. Quem? Com quem?
          Quando? Por quê? Como? Quanto? Qual prova?
        </p>
      </section>

      {poder ? (
        <section className="list-block">
          <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
            Mapa de poder 2026 (corte KB)
          </h2>
          {Object.entries(poder)
            .filter(([k]) => k !== "observacao")
            .map(([k, v]) => (
              <div key={k} className="list-item">
                <span className="item-title">{k}</span>
                <span className="item-meta">{v}</span>
              </div>
            ))}
          <p className="faint">{poder.observacao}</p>
        </section>
      ) : null}

      <p className="faint">
        API: <Link href="/api/v1/health">/api/v1/health</Link> · Dados:{" "}
        <code>data/atlas-brasil-kb-v2.json</code>
      </p>
    </div>
  );
}
