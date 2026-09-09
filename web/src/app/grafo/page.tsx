import Link from "next/link";
import {
  macroClusters,
  inducedSubgraph,
  GRAPH_LIMITS,
  PATH_DISCLAIMER,
  resolveDocument,
} from "@/lib/graph-engine";
import { visualGraph, type GraphMode } from "@/lib/visual-graph";
import { labelOf } from "@/lib/kb";
import { hubsRanking } from "@/lib/network-metrics";
import TemporalControls from "@/components/TemporalControls";
import InteractiveGraph from "@/components/InteractiveGraph";

const MODOS: { id: GraphMode; label: string }[] = [
  { id: "resumo", label: "Resumo" },
  { id: "politica", label: "Política" },
  { id: "dinheiro", label: "Dinheiro" },
  { id: "empresas", label: "Empresas" },
  { id: "justica", label: "Justiça" },
  { id: "completo", label: "Completo" },
];

const GRAUS = [
  { value: "", label: "Todos os graus" },
  { value: "fato_documentado", label: "Fato documentado" },
  { value: "decisao_judicial", label: "Decisão judicial" },
  { value: "relatorio_oficial", label: "Relatório oficial" },
  { value: "alegacao_sem_prova", label: "Alegação sem prova" },
  { value: "hipotese_jornalistica", label: "Hipótese jornalística" },
];

function modoHref(
  centro: string,
  modo: GraphMode,
  extra?: { expand?: string; de?: string; ate?: string; grau?: string }
) {
  const p = new URLSearchParams();
  p.set("centro", centro);
  p.set("modo", modo);
  if (extra?.expand) p.set("expand", extra.expand);
  if (extra?.de) p.set("de", extra.de);
  if (extra?.ate) p.set("ate", extra.ate);
  if (extra?.grau) p.set("grau", extra.grau);
  return `/grafo?${p.toString()}`;
}

export default function GrafoPage({
  searchParams,
}: {
  searchParams: {
    centro?: string;
    profundidade?: string;
    modo?: string;
    expand?: string;
    de?: string;
    ate?: string;
    ano?: string;
    grau?: string;
    max_nodes?: string;
    max_edges?: string;
  };
}) {
  const temCentro = Boolean(searchParams.centro);
  const modoParam = (searchParams.modo ||
    (temCentro ? "resumo" : "macro")) as GraphMode | "macro";
  const de = searchParams.de || "1985";
  const ate = searchParams.ate || searchParams.ano || "2026";
  const grau = searchParams.grau;
  const maxNodes = Math.min(
    GRAPH_LIMITS.hard_nodes,
    Math.max(
      GRAPH_LIMITS.initial_nodes,
      Number(searchParams.max_nodes || GRAPH_LIMITS.initial_nodes) ||
        GRAPH_LIMITS.initial_nodes
    )
  );
  const topHubs = hubsRanking("degree", {
    limit: GRAPH_LIMITS.macro_hubs,
  }).ranking;

  if (modoParam === "macro" || (!temCentro && !searchParams.modo)) {
    const { clusters, edge_count } = macroClusters();
    const hubIds = topHubs.map((h) => h.id);
    const induced = inducedSubgraph(hubIds);

    return (
      <div className="stack">
        <div>
          <p className="eyebrow">Rede · FASE 8</p>
          <h1 className="section-title">Grafo de Relações</h1>
          <p className="muted">
            Visão macro: top {hubIds.length} hubs (
            {edge_count.toLocaleString("pt-BR")} arestas na KB). Clique um hub
            para zoom semântico (Política / Dinheiro / Empresas / Justiça).
          </p>
        </div>
        <div className="chips">
          <Link className="chip" href="/grafo/hubs">
            Hubs
          </Link>
          <Link className="chip" href="/grafo/comunidades">
            Comunidades
          </Link>
          <Link className="chip" href="/grafo/conexao">
            Conexão
          </Link>
          <Link className="chip" href="/grafo/encontros">
            Encontros
          </Link>
          <Link className="chip" href="/investigar">
            Investigar
          </Link>
        </div>
        <div className="graph-layout">
          <div className="graph-canvas-wrap">
            <InteractiveGraph
              nodes={induced.nodes}
              edges={induced.edges}
              centro={hubIds[0]}
            />
          </div>
          <aside className="graph-side">
            <div className="panel">
              <h2>Hubs (abrir resumo)</h2>
              <div
                className="chips"
                style={{ flexDirection: "column", alignItems: "stretch" }}
              >
                {topHubs.map((h) => (
                  <Link
                    key={h.id}
                    className="chip"
                    href={modoHref(h.id, "resumo", { ate })}
                  >
                    #{h.rank} {h.nome}
                  </Link>
                ))}
              </div>
            </div>
            <div className="panel">
              <h2>Clusters</h2>
              {Object.entries(clusters)
                .filter(([, nodes]) => nodes.length > 0)
                .slice(0, 6)
                .map(([key, nodes]) => (
                  <div key={key} style={{ marginBottom: "0.65rem" }}>
                    <p
                      className="item-title"
                      style={{ textTransform: "capitalize" }}
                    >
                      {key.replace(/_/g, " ")} ({nodes.length})
                    </p>
                    <div className="chips" style={{ marginTop: "0.35rem" }}>
                      {nodes.slice(0, 4).map((n) => (
                        <Link
                          key={n.id}
                          className="chip"
                          href={modoHref(n.id, "resumo")}
                        >
                          {n.nome}
                        </Link>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          </aside>
        </div>
        <p className="prose-note">{PATH_DISCLAIMER}</p>
      </div>
    );
  }

  const centro = searchParams.centro!;
  const modo = (["resumo", "politica", "dinheiro", "empresas", "justica", "completo"].includes(
    modoParam
  )
    ? modoParam
    : "resumo") as GraphMode;
  const expand = searchParams.expand || null;

  const vg = visualGraph({
    focal: centro,
    mode: modo,
    expand,
    max_nodes: maxNodes,
    de,
    ate,
  });

  let edges = vg.edges;
  if (grau) {
    edges = edges.filter((e) => (e.grau_confirmacao || "") === grau);
  }
  const nodes = vg.nodes;

  return (
    <div className="stack">
      <div>
        <p className="eyebrow">Grafo · zoom semântico</p>
        <h1 className="section-title">{labelOf(centro)}</h1>
        <p className="muted">
          Modo {modo}
          {expand ? ` · ${expand}` : ""} · {nodes.length} nós · {edges.length}{" "}
          arestas
          {vg.hidden_count
            ? ` · ${vg.hidden_count} em supernós / omitidos`
            : ""}{" "}
          · {de}–{ate}
        </p>
      </div>

      <div className="chips">
        <Link className="chip" href="/grafo">
          ← Macro
        </Link>
        {MODOS.map((m) => (
          <Link
            key={m.id}
            className={`chip${modo === m.id && !expand ? " active" : ""}`}
            href={modoHref(centro, m.id, { de, ate, grau })}
          >
            {m.label}
            {m.id !== "resumo" && m.id !== "completo"
              ? ` · ${vg.domain_counts[m.id as keyof typeof vg.domain_counts] || 0}`
              : ""}
          </Link>
        ))}
      </div>

      {vg.expandable_groups.length > 0 ? (
        <div className="chips">
          {vg.expandable_groups.map((g) => (
            <Link
              key={g.id}
              className="chip"
              href={modoHref(centro, g.mode, {
                expand: g.expand,
                de,
                ate,
                grau,
              })}
            >
              Expandir {g.label} ({g.count})
            </Link>
          ))}
          {expand ? (
            <Link className="chip" href={modoHref(centro, modo, { de, ate, grau })}>
              Recolher subtype
            </Link>
          ) : null}
        </div>
      ) : null}

      <TemporalControls
        centro={centro}
        profundidade={1}
        ano={Number(ate) || 2026}
        modo={modo}
        expand={expand}
      />

      <div className="graph-layout">
        <div className="graph-canvas-wrap">
          <InteractiveGraph nodes={nodes} edges={edges} centro={centro} />
        </div>
        <aside className="graph-side">
          <div className="panel filter-block">
            <h2>Filtros</h2>
            <form method="get">
              <input type="hidden" name="centro" value={centro} />
              <input type="hidden" name="modo" value={modo} />
              {expand ? <input type="hidden" name="expand" value={expand} /> : null}
              <input type="hidden" name="de" value={de} />
              <input type="hidden" name="ate" value={ate} />
              <label className="faint">Grau de confirmação</label>
              <select name="grau" defaultValue={grau || ""}>
                {GRAUS.map((g) => (
                  <option key={g.value || "all"} value={g.value}>
                    {g.label}
                  </option>
                ))}
              </select>
              <button
                className="btn-primary"
                type="submit"
                style={{ width: "100%", marginTop: "0.85rem" }}
              >
                Aplicar
              </button>
            </form>
          </div>
          <div className="panel">
            <h2>Contagens por domínio</h2>
            <div className="list-block">
              {(Object.entries(vg.domain_counts) as [string, number][]).map(
                ([k, n]) => (
                  <div key={k} className="list-item">
                    <p className="item-title" style={{ textTransform: "capitalize" }}>
                      {k}
                    </p>
                    <p className="item-meta">{n} relações (1 hop)</p>
                  </div>
                )
              )}
            </div>
          </div>
          <div className="panel">
            <h2>Reason codes</h2>
            <p className="faint">{vg.reason_codes.join(" · ")}</p>
          </div>
        </aside>
      </div>

      <section className="panel">
        <h2>Arestas no canvas</h2>
        <p className="muted">
          Para ver tudo: use listas do perfil (Dinheiro / Empresas), não milhares
          de nós no grafo.
        </p>
        <div className="list-block">
          {edges.slice(0, 40).map((e) => (
            <div key={e.id} className="list-item">
              <p className="item-title">
                {labelOf(e.from)} → {labelOf(e.to)}
              </p>
              <p className="item-meta">
                {e.tipo} · {e.grau_confirmacao} · {e.periodo}
              </p>
              <p className="muted">
                {e.justificativa_documental || e.contexto}
              </p>
              <p className="faint">
                {(e.fonte_ids || []).map((fid, i) => {
                  const d = resolveDocument(fid);
                  const url = d?.url || d?.url_ref;
                  return (
                    <span key={fid}>
                      {i > 0 ? " · " : ""}
                      {url?.startsWith("http") ? (
                        <a href={url} target="_blank" rel="noreferrer">
                          {d?.titulo || fid}
                        </a>
                      ) : (
                        <Link href={`/fontes/${fid}`}>{d?.titulo || fid}</Link>
                      )}
                    </span>
                  );
                })}
              </p>
            </div>
          ))}
          {edges.length === 0 ? (
            <p className="muted">Sem arestas neste modo/filtro.</p>
          ) : null}
        </div>
      </section>
      <p className="prose-note">{PATH_DISCLAIMER}</p>
    </div>
  );
}
