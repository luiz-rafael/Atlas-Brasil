import { NextRequest, NextResponse } from "next/server";
import { shortestPath } from "@/lib/graph-engine";
import { pingNeo4j } from "@/lib/neo4j";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const a = sp.get("a");
  const b = sp.get("b");
  const max = Math.min(8, Math.max(2, Number(sp.get("max") || 6)));
  if (!a || !b) {
    return NextResponse.json(
      { error: "Parâmetros a e b são obrigatórios" },
      { status: 400 }
    );
  }
  const neo = await pingNeo4j();
  return NextResponse.json({ ...shortestPath(a, b, max), neo4j: neo });
}
