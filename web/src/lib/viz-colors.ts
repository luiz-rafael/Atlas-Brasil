/**
 * ATLAS INK — cores de entidade/relação (dessaturadas, território BR).
 * Nunca depender só da cor; forma/label também comunicam tipo.
 */

export const ENTITY_COLOR: Record<string, string> = {
  pessoa: "#D5C7A4",
  empresa: "#4E7C72",
  partido: "#807167",
  instituicao: "#55738B",
  caso: "#76667F",
  faccao: "#76667F",
  operacao: "#8B6C91",
  grupo: "#66736F",
  supernode: "#8A918B",
  mandato: "#9A7645",
  estado: "#A05E48",
  emenda: "#B08B44",
  contrato: "#4E7C72",
  licitacao: "#A47B32",
  transferencia: "#B39645",
};

export const REL_COLOR: Record<string, string> = {
  politico: "#D5C7A4",
  financeira: "#B08B44",
  societaria: "#4E7C72",
  institucional: "#55738B",
  investigacao: "#76667F",
  documental: "#8A918B",
  pessoal: "#AEB8B4",
  territorial: "#A05E48",
};

export function colorForEntity(tipo: string): string {
  return ENTITY_COLOR[tipo] || "#66736F";
}

export function colorForRelation(tipo: string): string {
  const t = (tipo || "").toLowerCase();
  if (
    t.startsWith("agrega_dinheiro") ||
    t.includes("doacao") ||
    t.includes("financ") ||
    t.includes("contrato") ||
    t.includes("pagamento") ||
    t.includes("despesa") ||
    t.includes("emenda") ||
    t.includes("campanha")
  )
    return REL_COLOR.financeira;
  if (
    t.startsWith("agrega_empresas") ||
    t.includes("socio") ||
    t.includes("empres") ||
    t.includes("fornecid") ||
    t.includes("licit")
  )
    return REL_COLOR.societaria;
  if (
    t.startsWith("agrega_politica") ||
    t.includes("partido") ||
    t.includes("eleitor") ||
    t.includes("cargo") ||
    t.includes("governo") ||
    t.includes("mandato") ||
    t.includes("proposic") ||
    t.includes("membro")
  )
    return REL_COLOR.politico;
  if (
    t.startsWith("agrega_justica") ||
    t.includes("investig") ||
    t.includes("operacao") ||
    t.includes("indicia") ||
    t.includes("denuncia") ||
    t.includes("participou")
  )
    return REL_COLOR.investigacao;
  if (t.includes("stf") || t.includes("tse") || t.includes("orgao") || t.includes("instit"))
    return REL_COLOR.institucional;
  if (t.includes("documento") || t.includes("fonte")) return REL_COLOR.documental;
  if (t.includes("territorio") || t.includes("municipio") || t.includes("uf"))
    return REL_COLOR.territorial;
  return REL_COLOR.pessoal;
}

export function hrefForEntity(id: string, tipo: string): string {
  if (tipo === "supernode" || id.startsWith("sn::")) {
    const parts = id.split("::");
    if (parts[0] === "sn" && parts.length >= 3) {
      const domain = parts[1];
      if (parts.length === 3) {
        const centro = parts[2];
        return `/grafo?centro=${encodeURIComponent(centro)}&modo=${domain}`;
      }
      const expand = parts[2];
      const centro = parts.slice(3).join("::");
      return `/grafo?centro=${encodeURIComponent(
        centro
      )}&modo=${domain}&expand=${encodeURIComponent(expand)}`;
    }
    return "/grafo";
  }
  if (tipo === "grupo" || id.startsWith("grp_")) {
    const m = id.match(/^grp_[^_]+_(.+)$/);
    const centro = m?.[1];
    if (centro) {
      return `/grafo?centro=${encodeURIComponent(
        centro
      )}&modo=completo&profundidade=1&max_nodes=50`;
    }
    return "/grafo";
  }
  if (tipo === "pessoa") return `/pessoas/${id}`;
  if (tipo === "empresa") return `/empresas/${id}`;
  if (tipo === "partido") return `/partidos/${id}`;
  if (tipo === "instituicao") return `/instituicoes/${id}`;
  if (tipo === "caso" || id.startsWith("c_")) return `/casos/${id}`;
  return `/grafo?centro=${encodeURIComponent(id)}&modo=resumo`;
}
