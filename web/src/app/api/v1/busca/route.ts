import { NextRequest, NextResponse } from "next/server";
import { buscaAvancada } from "@/lib/graph-engine";

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q") || "";
  return NextResponse.json(buscaAvancada(q));
}
