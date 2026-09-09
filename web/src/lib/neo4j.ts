import neo4j, { Driver, Session } from "neo4j-driver";

let driver: Driver | null = null;
let availability: "unknown" | "up" | "down" = "unknown";

export function neo4jConfigured(): boolean {
  return Boolean(process.env.NEO4J_URI || process.env.NEO4J_PASSWORD);
}

export function getDriver(): Driver | null {
  if (availability === "down") return null;
  const uri = process.env.NEO4J_URI || "bolt://localhost:7687";
  const user = process.env.NEO4J_USER || "neo4j";
  const password = process.env.NEO4J_PASSWORD || "atlasbrasil";
  if (!driver) {
    driver = neo4j.driver(uri, neo4j.auth.basic(user, password), {
      connectionTimeout: 3000,
    });
  }
  return driver;
}

export async function withNeo4j<T>(
  fn: (session: Session) => Promise<T>
): Promise<{ ok: true; data: T } | { ok: false; error: string }> {
  const d = getDriver();
  if (!d) return { ok: false, error: "Neo4j não configurado" };
  const session = d.session();
  try {
    const data = await fn(session);
    availability = "up";
    return { ok: true, data };
  } catch (e) {
    availability = "down";
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  } finally {
    await session.close();
  }
}

export async function pingNeo4j(): Promise<boolean> {
  const res = await withNeo4j(async (s) => {
    await s.run("RETURN 1 AS ok");
    return true;
  });
  return res.ok;
}

export function resetNeo4jAvailability() {
  availability = "unknown";
}
