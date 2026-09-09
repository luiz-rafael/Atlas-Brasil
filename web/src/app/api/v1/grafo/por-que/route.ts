import { NextRequest, NextResponse } from "next/server";
import { whyConnected } from "@/lib/graph-engine";
import { pingNeo4j } from "@/lib/neo4j";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const a = sp.get("a");
  const b = sp.get("b");
  if (!a || !b) {
    return NextResponse.json(
      { error: "Parâmetros a e b são obrigatórios" },
      { status: 400 }
    );
  }
  const neo = await pingNeo4j();
  return NextResponse.json({ ...whyConnected(a, b), neo4j: neo });
}
