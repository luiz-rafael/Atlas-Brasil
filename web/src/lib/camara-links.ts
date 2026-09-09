/** Links oficiais Câmara — preferir portal humano à API. */

export function camaraIdFromPessoa(sourceIds?: string[] | null, entityId?: string) {
  for (const s of sourceIds || []) {
    if (String(s).startsWith("cam:")) return String(s).slice(4);
  }
  if (entityId?.startsWith("p_cam_")) return entityId.slice(6);
  return null;
}

export function camaraProposicaoUrl(idProposicao?: string | null) {
  if (!idProposicao) return null;
  const id = String(idProposicao).replace(/^prop:/, "");
  if (!/^\d+$/.test(id)) return null;
  return `https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=${id}`;
}

export function camaraVotacaoApiUrl(idVotacao?: string | null) {
  if (!idVotacao) return null;
  return `https://dadosabertos.camara.leg.br/api/v2/votacoes/${encodeURIComponent(
    String(idVotacao)
  )}`;
}

export function camaraPresencaPlenarioUrl(
  deputadoId: string,
  ano = new Date().getFullYear()
) {
  return `https://www.camara.leg.br/deputados/${deputadoId}/presenca-plenario/${ano}`;
}

export function propLabel(opts: {
  label?: string | null;
  titulo?: string | null;
  sigla?: string | null;
  tipo?: string | null;
  numero?: string | number | null;
  ano?: string | number | null;
  id?: string | null;
}) {
  if (opts.label) return opts.label;
  if (opts.titulo && !/^\d+$/.test(String(opts.titulo).trim())) return opts.titulo;
  const sigla = opts.sigla || opts.tipo || "";
  const num = opts.numero ?? "";
  const ano = opts.ano ?? "";
  const composed = `${sigla} ${num}/${ano}`.replace(/\s+/g, " ").trim();
  if (composed && composed !== "/" && !composed.endsWith("/")) return composed;
  if (sigla && num !== "") return `${sigla} ${num}`.trim();
  return opts.titulo || opts.id || "Proposição";
}
