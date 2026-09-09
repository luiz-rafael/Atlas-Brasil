import { readFileSync, existsSync } from "fs";
import path from "path";
import VisaoDashboard from "@/components/VisaoDashboard";
import { getKB } from "@/lib/kb";

function loadCoverage() {
  const candidates = [
    path.join(process.cwd(), "pipelines", "reports", "coverage_f2.json"),
    path.join(process.cwd(), "pipelines", "reports", "coverage_f1.json"),
    path.join(process.cwd(), "..", "pipelines", "reports", "coverage_f2.json"),
  ];
  for (const p of candidates) {
    if (!existsSync(p)) continue;
    try {
      const j = JSON.parse(readFileSync(p, "utf-8"));
      const sources = j.sources || [];
      const ingested = sources.filter((s: { last_ingested_at?: string }) =>
        Boolean(s.last_ingested_at)
      ).length;
      return {
        total: j.total_sources || sources.length,
        active: (j.por_status || {}).active || 0,
        ingested,
        porStatus: j.por_status || {},
      };
    } catch {
      /* ignore */
    }
  }
  return null;
}

export default function VisaoPage() {
  const kb = getKB();
  const pessoas = kb.entidades.filter((e) => e.tipo === "pessoa" && !e.isolada).length;
  const empresas = kb.entidades.filter((e) => e.tipo === "empresa").length;
  const docs = (kb.documentos || []).length;
  const rels = (kb.relacoes || []).length;
  const casos = (kb.casos || []).length;
  const instituicoes = kb.entidades.filter((e) => e.tipo === "instituicao").length;
  const contratos = kb.entidades.filter((e) => e.tipo === "contrato").length;
  const comBens = kb.entidades.filter((e) => e.bens_declarados).length;
  const crime = kb.entidades.filter(
    (e) =>
      e.tipo === "faccao" ||
      (e.tags || []).some((t) => /crime|pcc|cv/i.test(t))
  ).length;
  const coverage = loadCoverage();
  const er = (kb.meta as { er_casas_tse?: { matched?: number } } | undefined)
    ?.er_casas_tse;

  return (
    <VisaoDashboard
      stats={{
        pessoas,
        empresas,
        docs,
        rels,
        casos,
        instituicoes,
        crime,
        contratos,
        comBens,
        versao: String(kb.meta?.versao || "—"),
      }}
      coverage={coverage}
      kb={{
        entidades: kb.entidades.map((e) => ({
          id: e.id,
          tipo: e.tipo,
          uf: e.uf,
          isolada: e.isolada,
          tags: e.tags,
          nome: e.nome,
          cargo_atual: e.cargo_atual,
        })),
        relacoes: kb.relacoes.map((r) => ({
          origem: r.origem,
          destino: r.destino,
          tipo: r.tipo,
        })),
      }}
      updates={[
        {
          title: `ER bens TSE → Casas (${er?.matched ?? "—"})`,
          when: "agora",
          href: "/pessoas",
        },
        { title: "Contratos PNCP na KB", when: "Onda F2", href: "/dinheiro" },
        { title: "Cobertura de fontes", when: "live", href: "/status" },
        { title: "GraphRAG disponível", when: "agora", href: "/ia" },
      ]}
    />
  );
}
