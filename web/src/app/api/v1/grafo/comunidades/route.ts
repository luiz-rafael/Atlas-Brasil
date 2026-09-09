import { NextRequest, NextResponse } from "next/server";
import { detectCommunities, findBridges } from "@/lib/network-metrics";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const de = sp.get("de") || undefined;
  const ate = sp.get("ate") || undefined;
  const graus = sp.get("graus")?.split(",").filter(Boolean);
  const mode = sp.get("mode") || "comunidades";

  if (mode === "pontes") {
    return NextResponse.json(findBridges({ de, ate, graus }));
  }
  return NextResponse.json(detectCommunities({ de, ate, graus }));
}
