import { notFound } from "next/navigation";
import { fetchPessoaDetail } from "@/lib/pessoas";
import {
  entityById,
  registrosDePessoa,
  relacoesDe,
  casoById,
  slimPessoaForWeb,
  labelOf,
} from "@/lib/kb";
import { visualGraph } from "@/lib/visual-graph";
import ProfileView from "@/components/perfil/ProfileView";
import { parseProfileTab } from "@/components/perfil/tabs";
import type { Entidade, Relacao, Registro } from "@/lib/kb-types";

export default async function PessoaPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: { tab?: string };
}) {
  const tab = parseProfileTab(searchParams?.tab);
  const api = await fetchPessoaDetail(params.id);

  if (api?.pessoa) {
    return (
      <ProfileView
        initialTab={tab}
        pessoa={api.pessoa as unknown as Entidade}
        rels={api.rels as unknown as Relacao[]}
        regs={api.regs as unknown as Registro[]}
        casos={api.casos}
        labels={api.labels}
        fontes={api.fontes}
        graphNodes={api.graphNodes as never}
        graphEdges={api.graphEdges as never}
      />
    );
  }

  // Fallback KB se API offline
  const raw = entityById(params.id);
  if (!raw || raw.tipo !== "pessoa") notFound();

  const pessoa = slimPessoaForWeb(raw);
  const regs = registrosDePessoa(pessoa.id);
  const rels = relacoesDe(pessoa.id);

  const fontes = pessoa.perfil_fontes?.length
    ? pessoa.perfil_fontes
    : ([
        pessoa.pagina_oficial,
        ...(pessoa.source_ids || []).map((s) =>
          s.startsWith("cam:")
            ? `https://dadosabertos.camara.leg.br/api/v2/deputados/${s.slice(4)}`
            : s.startsWith("sen:")
              ? `https://www25.senado.leg.br/web/senadores/senador/-/perfil/${s.slice(4)}`
              : null
        ),
      ].filter(Boolean) as string[]);

  const g = visualGraph({ focal: pessoa.id, mode: "resumo" });
  const graphNodes = g.nodes;
  const graphEdges = g.edges;

  const casos: Record<string, { id: string; nome: string }> = {};
  for (const r of regs) {
    const c = casoById(r.caso_id);
    if (c) casos[c.id] = { id: c.id, nome: c.nome };
  }

  const labels: Record<string, string> = { [pessoa.id]: pessoa.nome };
  for (const r of rels) {
    labels[r.origem] = labels[r.origem] || labelOf(r.origem);
    labels[r.destino] = labels[r.destino] || labelOf(r.destino);
  }
  for (const n of graphNodes) {
    labels[n.id] = n.nome;
  }

  return (
    <ProfileView
      initialTab={tab}
      pessoa={pessoa}
      rels={rels}
      regs={regs}
      casos={casos}
      labels={labels}
      fontes={fontes}
      graphNodes={graphNodes}
      graphEdges={graphEdges}
    />
  );
}
