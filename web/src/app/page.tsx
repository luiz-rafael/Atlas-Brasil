import Link from "next/link";

const EXPLORE = [
  {
    href: "/pessoas",
    title: "Pessoas",
    text: "Parlamentares, executivo e trajetórias documentadas.",
  },
  {
    href: "/pessoas?escopo=congresso",
    title: "Congresso",
    text: "Deputados e senadores em exercício e históricos.",
  },
  {
    href: "/indicadores",
    title: "Território",
    text: "Indicadores oficiais por UF e município — observação, não causalidade.",
  },
  {
    href: "/pessoas?escopo=governadores",
    title: "Governos",
    text: "Governadores e mandatos com séries durante a administração.",
  },
  {
    href: "/empresas",
    title: "Empresas",
    text: "CNPJ, contratos e sanções administrativas.",
  },
  {
    href: "/dinheiro",
    title: "Dinheiro público",
    text: "Emendas, despesas parlamentares e contratos.",
  },
  {
    href: "/casos",
    title: "Processos",
    text: "Casos e menções documentais — sem acusar.",
  },
  {
    href: "/historias",
    title: "Histórias",
    text: "Narrativas curtas ligando entidades e fontes.",
  },
  {
    href: "/timeline",
    title: "Linha do tempo",
    text: "Eventos públicos em ordem cronológica.",
  },
];

const STORIES = [
  {
    href: "/historias#orcamento",
    title: "Do Orçamento ao beneficiário",
    text: "Como um recurso público aparece em emenda, contrato e documento.",
  },
  {
    href: "/historias#trajetoria",
    title: "Trajetória política documentada",
    text: "Mandatos, partidos e atividade legislativa em uma linha do tempo.",
  },
  {
    href: "/historias#conexao",
    title: "Relação documental entre entidades",
    text: "Caminhos explicáveis entre pessoa, empresa e instituição.",
  },
];

export default function HomePage() {
  return (
    <div className="home-atlas">
      <section className="home-hero">
        <p className="home-brand">ATLAS BRASIL</p>
        <h1>O que você quer entender sobre o Brasil?</h1>
        <p className="home-lead">
          Explore pessoas, empresas, instituições e documentos oficiais —
          com evidência, sem acusação.
        </p>
        <form className="home-search" action="/explorar" method="get">
          <label className="sr-only" htmlFor="home-q">
            Pesquisar
          </label>
          <input
            id="home-q"
            name="q"
            type="search"
            placeholder="Pesquisar pessoa, empresa, partido, instituição, contrato, processo…"
            autoComplete="off"
          />
          <button type="submit" className="btn-primary">
            Buscar
          </button>
        </form>
      </section>

      <section className="home-section">
        <h2>Explorar por</h2>
        <p className="muted">Escolha um ponto de entrada. Cada tela responde uma pergunta.</p>
        <div className="home-explore-grid">
          {EXPLORE.map((item) => (
            <Link key={item.href} href={item.href} className="home-explore-link">
              <strong>{item.title}</strong>
              <span>{item.text}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="home-section">
        <h2>Histórias em destaque</h2>
        <p className="muted">Leituras curtas, sem sensacionalismo — sempre com fonte.</p>
        <div className="home-story-list">
          {STORIES.map((s) => (
            <Link key={s.href} href={s.href} className="home-story-link">
              <strong>{s.title}</strong>
              <span>{s.text}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
