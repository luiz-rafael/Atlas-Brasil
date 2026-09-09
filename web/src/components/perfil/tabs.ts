export const PROFILE_TABS = [
  { id: "resumo", label: "Resumo" },
  { id: "trajetoria", label: "Trajetória" },
  { id: "mandatos", label: "Mandatos" },
  { id: "partidos", label: "Partidos" },
  { id: "eleicoes", label: "Eleições" },
  { id: "atuacao", label: "Atuação" },
  { id: "dinheiro", label: "Dinheiro" },
  { id: "relacoes", label: "Relações" },
  { id: "justica", label: "Justiça" },
  { id: "documentos", label: "Documentos" },
] as const;

export type ProfileTabId = (typeof PROFILE_TABS)[number]["id"];

/** URLs antigas → aba canônica (FASE 5). */
const TAB_ALIASES: Record<string, ProfileTabId> = {
  visao: "resumo",
  projetos: "atuacao",
  votacoes: "atuacao",
  remuneracao: "dinheiro",
  empresas: "relacoes",
  grafo: "relacoes",
};

export function parseProfileTab(raw?: string | null): ProfileTabId {
  const id = (raw || "resumo").toLowerCase();
  if (TAB_ALIASES[id]) return TAB_ALIASES[id];
  return PROFILE_TABS.some((t) => t.id === id)
    ? (id as ProfileTabId)
    : "resumo";
}

export function tabHref(pessoaId: string, tab: ProfileTabId) {
  if (tab === "resumo") return `/pessoas/${pessoaId}`;
  return `/pessoas/${pessoaId}?tab=${tab}`;
}
