import "server-only";
import fs from "fs";
import path from "path";
import type { InvestigacoesBetaMock } from "@/lib/investigacoes-beta-model";

export type {
  InvestigacoesBetaMock,
  MockCase,
  MockCaseCompanyLink,
  MockCompany,
  MockCourt,
  MockDecision,
  MockEvent,
  MockParticipation,
  MockPerson,
  MockSource,
} from "@/lib/investigacoes-beta-model";

export {
  ACTION_LABEL,
  NUCLEUS_LABEL,
  STATUS_LABEL,
  STATUS_TONE,
  buildInvestigacoesBetaGraph,
  companyOrCourtName,
  eventsForCase,
  hrefForBetaNode,
  latestStatusByPerson,
  participationsForCase,
  personName,
} from "@/lib/investigacoes-beta-model";

const CANDIDATES = [
  path.join(process.cwd(), "data", "mocks", "investigacoes_beta_lava_jato.json"),
  path.join(process.cwd(), "..", "data", "mocks", "investigacoes_beta_lava_jato.json"),
];

const FOTO_CANDIDATES = [
  path.join(process.cwd(), "data", "mocks", "investigacoes_beta_fotos.json"),
  path.join(process.cwd(), "..", "data", "mocks", "investigacoes_beta_fotos.json"),
];

let cache: InvestigacoesBetaMock | null = null;
let fotoCache: Record<string, string> | null = null;

function emptyInvestigacoesBeta(): InvestigacoesBetaMock {
  return {
    meta: {
      title: "Investigações BETA indisponível neste deploy",
      disclaimer: "Mock local ausente — página em modo vazio.",
      version: "0",
      kind: "DEMO_MOCK",
    },
    operation: { id: "none", name: "—", started_at: "" },
    organizations: [],
    parties: [],
    people: [],
    companies: [],
    courts: [],
    sources: [],
    case_company_links: [],
    cases: [],
    case_events: [],
    participations: [],
    decisions: [],
    reporters: [],
    dual_rails: [],
    anti_patterns: [],
    institutions_roles: [],
  };
}

export function loadInvestigacoesBeta(): InvestigacoesBetaMock {
  if (cache) return cache;
  for (const p of CANDIDATES) {
    if (fs.existsSync(p)) {
      cache = JSON.parse(fs.readFileSync(p, "utf8")) as InvestigacoesBetaMock;
      return cache;
    }
  }
  cache = emptyInvestigacoesBeta();
  return cache;
}

/** Fotos oficiais (KB) para nós pessoa do mock BETA. */
export function loadInvestigacoesBetaFotos(): Record<string, string> {
  if (fotoCache) return fotoCache;
  for (const p of FOTO_CANDIDATES) {
    if (!fs.existsSync(p)) continue;
    try {
      const raw = JSON.parse(fs.readFileSync(p, "utf8")) as {
        fotos?: Record<string, string>;
      };
      fotoCache = raw.fotos || {};
      return fotoCache;
    } catch {
      /* ignore */
    }
  }
  fotoCache = {};
  return fotoCache;
}
