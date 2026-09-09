import { NextRequest, NextResponse } from "next/server";
import { getKB } from "@/lib/kb";

export async function GET(req: NextRequest) {
  const caso = req.nextUrl.searchParams.get("caso_id");
  let list = getKB().fluxos_financeiros || [];
  if (caso) list = list.filter((f) => f.caso_id === caso);
  return NextResponse.json(list);
}
