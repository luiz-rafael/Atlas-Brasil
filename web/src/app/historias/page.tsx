import Link from "next/link";

const STORIES = [
  {
    id: "orcamento",
    title: "Do Orçamento ao beneficiário",
    lead: "Um caminho documental típico: emenda parlamentar, execução e contrato — sempre com fonte.",
    body: "O Atlas liga autor, emenda e, quando disponível, execução no Portal da Transparência. Emenda não é ilegalidade: é instrumento orçamentário. O papel da interface é mostrar o rastro, não julgar.",
  },
  {
    id: "trajetoria",
    title: "Trajetória política documentada",
    lead: "Mandatos, partido, proposições e presença em votações nominais em uma linha factual.",
    body: "Cada bloco do perfil político vem de dados abertos da Casa ou de coletas oficiais. Ausência de um campo significa lacuna na amostra — não conclusão sobre a pessoa.",
  },
  {
    id: "conexao",
    title: "Relação documental entre entidades",
    lead: "Caminhos explicáveis entre pessoa, empresa e instituição, com justificativa na aresta.",
    body: "Compartilhar um nó no grafo não implica compartilhar culpa. Use “Encontrar conexão” e leia a justificativa documental de cada aresta antes de interpretar.",
  },
  {
    id: "cobertura",
    title: "O que a base cobre — e o que ainda não",
    lead: "Transparência sobre lacunas: votações nominais ≠ todas as sessões; sanções ≠ condenação criminal.",
    body: "A página de Fontes e a Metodologia descrevem cobertura e limites. Preferimos empty state honesto a inventar completude.",
  },
  {
    id: "dinheiro-publico",
    title: "Cota, emendas e contratos",
    lead: "Três fluxos de dinheiro público com naturezas diferentes — separados na interface de propósito.",
    body: "Cota parlamentar, emendas e contratos com a administração não se misturam no mesmo indicador. Cada um tem fonte e disclaimer próprios.",
  },
];

export default function HistoriasPage() {
  return (
    <div className="page stack historias-page">
      <header className="historias-hero">
        <p className="eyebrow">Editorial</p>
        <h1 className="section-title">Histórias</h1>
        <p className="muted">
          Leituras curtas que explicam como o Atlas conecta entidades e documentos.
          Sem sensacionalismo; sempre com limite declarado.
        </p>
      </header>
      <div className="historias-list">
        {STORIES.map((s) => (
          <article key={s.id} id={s.id} className="historias-item">
            <h2>{s.title}</h2>
            <p className="historias-lead">{s.lead}</p>
            <p className="muted">{s.body}</p>
            <p className="faint">
              <Link href="/metodologia">Metodologia</Link>
              {" · "}
              <Link href="/explorar">Explorar</Link>
              {" · "}
              <Link href="/grafo">Grafo</Link>
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
