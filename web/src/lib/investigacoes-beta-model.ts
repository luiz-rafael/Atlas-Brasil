/** Utilitários client-safe do mock Investigações BETA (sem fs). */

import type { GEdge, GNode } from "@/components/InteractiveGraph";

export type MockPerson = {
  id: string;
  name: string;
  atlas_id?: string;
  party_id?: string;
  role_hint?: string;
};

export type MockCompany = {
  id: string;
  name: string;
  type: string;
  note?: string;
};

export type MockCourt = {
  id: string;
  name: string;
  type: string;
};

export type MockSource = {
  id: string;
  title: string;
  url: string;
  publisher?: string;
  case_ids?: string[];
  at?: string | null;
  note?: string;
};

export type MockCaseCompanyLink = {
  case_id: string;
  company_id: string;
  relation: string;
  note?: string;
};

export type MockDecision = {
  at: string;
  actor_id: string;
  body: string;
  action: string;
  case_id: string;
  person_ids?: string[];
  summary: string;
  source_id?: string;
};

export type MockCase = {
  id: string;
  number: string;
  title: string;
  nucleus: string;
  parent_id: string | null;
  operation_id: string;
};

export type MockParticipation = {
  id: string;
  person_id: string;
  case_id: string;
  status: string;
  valid_from?: string | null;
  valid_to?: string | null;
  note?: string | null;
  source_id?: string;
};

export type MockEvent = {
  id: string;
  case_id: string;
  type: string;
  at: string;
  summary: string;
  actor_id?: string;
  body?: string;
  person_ids?: string[];
  children?: string[];
  highlight?: boolean;
  source_url?: string;
};

export type InvestigacoesBetaMock = {
  meta: {
    title: string;
    disclaimer: string;
    version: string;
    kind: string;
    scope?: string;
  };
  operation: { id: string; name: string; started_at: string; scope_note?: string };
  organizations: { id: string; name: string; type: string }[];
  parties: { id: string; name: string; abbreviation: string }[];
  people: MockPerson[];
  companies?: MockCompany[];
  courts?: MockCourt[];
  sources?: MockSource[];
  case_company_links?: MockCaseCompanyLink[];
  cases: MockCase[];
  case_events: MockEvent[];
  participations: MockParticipation[];
  decisions?: MockDecision[];
  reporters: {
    person_id: string;
    case_ids: string[];
    valid_from: string | null;
    valid_to: string | null;
    role: string;
  }[];
  dual_rails: {
    person_id: string;
    name: string;
    political: { at: string; label: string; source: string }[];
    legal: { at: string; label: string; status: string }[];
  }[];
  anti_patterns: string[];
  institutions_roles: {
    actor_id: string;
    role: string;
    target_type: string;
    note: string;
  }[];
};

export const STATUS_LABEL: Record<string, string> = {
  INVESTIGATED: "Investigado",
  CHARGED: "Denunciado",
  CHARGE_REJECTED: "Rejeitado",
  ARCHIVED: "Arquivado",
  JURISDICTION_CHANGED: "Mudou de foro",
  ACQUITTED: "Absolvido",
  CONVICTED: "Condenado",
  MIXED: "Misto",
  SUSPENDED: "Suspenso",
};

export const STATUS_TONE: Record<string, string> = {
  INVESTIGATED: "badge-investigado",
  CHARGED: "badge-reu",
  CHARGE_REJECTED: "badge-absolvido",
  ARCHIVED: "badge-absolvido",
  JURISDICTION_CHANGED: "badge-citado",
  ACQUITTED: "badge-absolvido",
  CONVICTED: "badge-condenado",
  SUSPENDED: "badge-indiciado",
};

export const NUCLEUS_LABEL: Record<string, string> = {
  PT: "Núcleo PT",
  PP: "Núcleo PP",
  PMDB_SENADO: "Núcleo PMDB — Senado",
  PMDB_CAMARA: "Núcleo PMDB — Câmara",
};

export const ACTION_LABEL: Record<string, string> = {
  CASE_SPLIT: "Desmembrou",
  FILED_CHARGE: "Ofereceu denúncia",
  CHARGE_REJECTED: "Rejeitou denúncia",
  ARCHIVED: "Arquivou",
  JURISDICTION_CHANGED: "Alterou jurisdição",
  OPINED_REJECT: "Opinou pela rejeição",
  AUTHORIZATION_DENIED: "Negou autorização",
};

export function personName(mock: InvestigacoesBetaMock, id: string) {
  return mock.people.find((p) => p.id === id)?.name || id;
}

export function companyOrCourtName(mock: InvestigacoesBetaMock, id: string) {
  const co = mock.companies?.find((c) => c.id === id);
  if (co) return co.name;
  const ct = mock.courts?.find((c) => c.id === id);
  if (ct) return ct.name;
  const org = mock.organizations.find((o) => o.id === id);
  return org?.name || id;
}

export function participationsForCase(mock: InvestigacoesBetaMock, caseId: string) {
  return mock.participations.filter((p) => p.case_id === caseId);
}

export function eventsForCase(mock: InvestigacoesBetaMock, caseId: string) {
  return mock.case_events
    .filter((e) => e.case_id === caseId)
    .sort((a, b) => String(a.at).localeCompare(String(b.at)));
}

export function latestStatusByPerson(
  parts: MockParticipation[],
  mock?: InvestigacoesBetaMock
) {
  const order = [
    "CONVICTED",
    "ACQUITTED",
    "CHARGE_REJECTED",
    "ARCHIVED",
    "JURISDICTION_CHANGED",
    "SUSPENDED",
    "CHARGED",
    "INVESTIGATED",
  ];
  const by = new Map<string, MockParticipation[]>();
  for (const p of parts) {
    const arr = by.get(p.person_id) || [];
    arr.push(p);
    by.set(p.person_id, arr);
  }
  const out: { person_id: string; latest: MockParticipation; history: MockParticipation[] }[] =
    [];
  for (const [person_id, history] of Array.from(by.entries())) {
    const sorted = [...history].sort((a, b) => {
      const ta = a.valid_from || "";
      const tb = b.valid_from || "";
      if (ta !== tb) return tb.localeCompare(ta);
      return order.indexOf(a.status) - order.indexOf(b.status);
    });
    out.push({ person_id, latest: sorted[0], history: sorted });
  }
  return out.sort((a, b) => {
    const na = mock ? personName(mock, a.person_id) : a.person_id;
    const nb = mock ? personName(mock, b.person_id) : b.person_id;
    return na.localeCompare(nb, "pt-BR");
  });
}

function entityNodeTipo(type: string): string {
  if (type === "company") return "empresa";
  if (type === "government_org" || type === "legislature") return "instituicao";
  if (type === "court" || type === "court_body") return "instituicao";
  return "instituicao";
}

export function buildInvestigacoesBetaGraph(
  mock: InvestigacoesBetaMock,
  opts?: {
    caseId?: string | null;
    mode?: "full" | "case";
    /** Mapa id→foto oficial (Camara/Senado) para nós pessoa. */
    photos?: Record<string, string>;
  }
): { nodes: GNode[]; edges: GEdge[] } {
  const mode = opts?.mode || "full";
  const focusCase = opts?.caseId || null;

  const caseIds = new Set<string>();
  if (mode === "case" && focusCase) {
    caseIds.add(focusCase);
    const c = mock.cases.find((x) => x.id === focusCase);
    if (c?.parent_id) caseIds.add(c.parent_id);
    mock.cases.filter((x) => x.parent_id === focusCase).forEach((x) => caseIds.add(x.id));
  } else {
    mock.cases.forEach((c) => caseIds.add(c.id));
  }

  const nodes: GNode[] = [];
  const edges: GEdge[] = [];
  const seenN = new Set<string>();
  const seenE = new Set<string>();

  const photos = opts?.photos || {};
  const addN = (id: string, nome: string, tipo: string) => {
    if (seenN.has(id)) return;
    seenN.add(id);
    const image =
      tipo === "pessoa" && photos[id] ? photos[id] : undefined;
    nodes.push({ id, nome, tipo, image });
  };
  const addE = (
    id: string,
    from: string,
    to: string,
    tipo: string,
    grau: string = "fato_documentado"
  ) => {
    if (seenE.has(id) || !seenN.has(from) || !seenN.has(to)) return;
    seenE.add(id);
    edges.push({ id, from, to, tipo, grau_confirmacao: grau });
  };

  addN(mock.operation.id, mock.operation.name, "operacao");
  for (const org of mock.organizations) addN(org.id, org.name, "instituicao");
  for (const party of mock.parties) {
    addN(party.id, party.abbreviation || party.name, "partido");
  }
  for (const c of mock.cases) {
    if (!caseIds.has(c.id)) continue;
    addN(c.id, c.number, "caso");
  }

  // Empresas / órgãos citados (contextuais — não culpa)
  for (const co of mock.companies || []) {
    addN(co.id, co.name, entityNodeTipo(co.type));
  }
  for (const ct of mock.courts || []) {
    // Evitar duplicar JFDF se já veio de organizations
    if (ct.id === "court_jfdf" && seenN.has("org_jfdf")) continue;
    addN(ct.id, ct.name, "instituicao");
  }

  if (caseIds.has("stf_inq_3989")) {
    addE("e_op_3989", mock.operation.id, "stf_inq_3989", "originou");
  }
  for (const c of mock.cases) {
    if (!c.parent_id || !caseIds.has(c.id) || !caseIds.has(c.parent_id)) continue;
    addE(`e_split_${c.parent_id}_${c.id}`, c.parent_id, c.id, "desmembrou_em");
  }
  for (const cid of Array.from(caseIds)) {
    addE(`e_pf_${cid}`, "org_pf", cid, "realizou_diligencias");
    addE(`e_pgr_${cid}`, "org_pgr", cid, "promoveu_investigacao");
    addE(`e_stf_${cid}`, cid, "org_stf", "processado_por");
  }

  const allowedRelations = new Set([
    "mentioned_in_context",
    "contrato_contexto",
    "orgao_contexto",
  ]);
  for (const link of mock.case_company_links || []) {
    if (!caseIds.has(link.case_id)) continue;
    const targetId =
      link.company_id === "court_jfdf" && seenN.has("org_jfdf")
        ? "org_jfdf"
        : link.company_id;
    if (!seenN.has(targetId)) continue;
    const rel = allowedRelations.has(link.relation)
      ? link.relation
      : "mentioned_in_context";
    addE(
      `e_ctx_${link.case_id}_${targetId}_${rel}`,
      link.case_id,
      targetId,
      rel,
      "contexto_documental_nao_culpa"
    );
  }

  for (const r of mock.reporters) {
    const p = mock.people.find((x) => x.id === r.person_id);
    addN(r.person_id, p?.name || r.person_id, "pessoa");
    for (const cid of r.case_ids) {
      if (!caseIds.has(cid)) continue;
      addE(`e_rel_${r.person_id}_${cid}`, r.person_id, cid, "relator_de");
    }
  }

  const janot = mock.people.find((x) => x.id === "person_rodrigo_janot");
  if (janot) {
    addN(janot.id, janot.name, "pessoa");
    addE("e_janot_pgr", janot.id, "org_pgr", "exerceu_cargo");
  }
  const lindora = mock.people.find((x) => x.id === "person_lindora_araujo");
  if (lindora) {
    addN(lindora.id, lindora.name, "pessoa");
    addE("e_lindora_pgr", lindora.id, "org_pgr", "exerceu_cargo");
  }
  for (const actorId of [
    "person_gilmar_mendes",
    "person_marco_aurelio",
  ] as const) {
    const a = mock.people.find((x) => x.id === actorId);
    if (!a) continue;
    addN(a.id, a.name, "pessoa");
    addE(`e_${actorId}_stf`, a.id, "org_stf", "exerceu_cargo");
  }

  const latest = new Map<string, MockParticipation>();
  for (const p of mock.participations) {
    if (!caseIds.has(p.case_id)) continue;
    const key = `${p.person_id}::${p.case_id}`;
    const prev = latest.get(key);
    if (!prev || String(p.valid_from || "") >= String(prev.valid_from || "")) {
      latest.set(key, p);
    }
  }

  const statusToEdge: Record<string, string> = {
    INVESTIGATED: "investigado_em",
    CHARGED: "denunciado_em",
    CHARGE_REJECTED: "denuncia_rejeitada_em",
    ARCHIVED: "arquivado_em",
    JURISDICTION_CHANGED: "jurisdicao_alterada_em",
    ACQUITTED: "absolvido_em",
    CONVICTED: "condenado_em",
    SUSPENDED: "suspenso_em",
  };

  for (const p of Array.from(latest.values())) {
    const person = mock.people.find((x) => x.id === p.person_id);
    if (!person) continue;
    const nodeId = person.atlas_id || person.id;
    addN(nodeId, person.name, "pessoa");
    if (person.party_id && seenN.has(person.party_id)) {
      addE(`e_party_${nodeId}_${person.party_id}`, nodeId, person.party_id, "filiado_a");
    }
    const edgeTipo = statusToEdge[p.status] || "participou_de";
    addE(
      `e_part_${nodeId}_${p.case_id}_${p.status}`,
      nodeId,
      p.case_id,
      edgeTipo,
      p.status === "CHARGE_REJECTED" ||
        p.status === "ARCHIVED" ||
        p.status === "ACQUITTED"
        ? "desfecho_favoravel_ou_arquivamento"
        : "fato_documentado"
    );
  }

  return { nodes, edges };
}

export function hrefForBetaNode(node: { id: string; tipo: string }): string | null {
  if (node.tipo === "caso" || node.id.startsWith("stf_inq_")) {
    return `/investigacoes-beta?caso=${encodeURIComponent(node.id)}`;
  }
  if (node.tipo === "operacao" || node.id === "operation_lava_jato") {
    return `/investigacoes-beta`;
  }
  if (node.tipo === "pessoa") {
    if (node.id.startsWith("p_")) return `/pessoas/${node.id}`;
    return null;
  }
  if (node.tipo === "partido") return `/partidos/${node.id}`;
  if (node.tipo === "empresa") return `/empresas/${node.id}`;
  if (node.tipo === "instituicao") return `/instituicoes/${node.id}`;
  return `/investigacoes-beta`;
}
