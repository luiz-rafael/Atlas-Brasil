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
  path.join(process.cwd(), "..", "data", "mocks", "investigacoes_beta_lava_jato.json"),
  path.join(process.cwd(), "data", "mocks", "investigacoes_beta_lava_jato.json"),
];

const FOTO_CANDIDATES = [
  path.join(process.cwd(), "..", "data", "mocks", "investigacoes_beta_fotos.json"),
  path.join(process.cwd(), "data", "mocks", "investigacoes_beta_fotos.json"),
];

let cache: InvestigacoesBetaMock | null = null;
let fotoCache: Record<string, string> | null = null;

export function loadInvestigacoesBeta(): InvestigacoesBetaMock {
  if (cache) return cache;
  for (const p of CANDIDATES) {
    if (fs.existsSync(p)) {
      cache = JSON.parse(fs.readFileSync(p, "utf8")) as InvestigacoesBetaMock;
      return cache;
    }
  }
  throw new Error("Mock investigacoes_beta_lava_jato.json não encontrado");
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
