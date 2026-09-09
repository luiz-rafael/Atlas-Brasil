import { NextRequest, NextResponse } from "next/server";
import { macroClusters, subgraph } from "@/lib/graph-engine";
import { visualGraph } from "@/lib/visual-graph";
import { pingNeo4j } from "@/lib/neo4j";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const centro = sp.get("centro_id") || sp.get("centro");
  const modo = sp.get("modo") || (centro && centro !== "macro" ? "resumo" : "macro");
  const expand = sp.get("expand");
  const profundidade = Math.min(
    3,
    Math.max(1, Number(sp.get("profundidade") || 1))
  );
  const de = sp.get("de") || undefined;
  const ate = sp.get("ate") || undefined;
  const tipos = sp.get("tipos")?.split(",").filter(Boolean);
  const maxNodes = Number(sp.get("max_nodes") || 25);
  const neo = await pingNeo4j();

  if (!centro || centro === "macro" || modo === "macro") {
    return NextResponse.json({
      ...macroClusters(),
      modo: "macro",
      neo4j: neo,
    });
  }

  if (modo === "hop" || modo === "legacy") {
    return NextResponse.json({
      ...subgraph(centro, profundidade, { de, ate, tipos }),
      modo: "hop",
      neo4j: neo,
    });
  }

  return NextResponse.json({
    ...visualGraph({
      focal: centro,
      mode: modo,
      expand,
      max_nodes: maxNodes,
      de,
      ate,
    }),
    neo4j: neo,
  });
}
