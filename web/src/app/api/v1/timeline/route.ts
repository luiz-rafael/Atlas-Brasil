import { NextRequest, NextResponse } from "next/server";
import { getKB } from "@/lib/kb";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  let items = getKB().timeline;
  const eixo = sp.get("eixo");
  const governo_id = sp.get("governo_id");
  if (eixo) items = items.filter((t) => t.eixo === eixo);
  if (governo_id) items = items.filter((t) => t.governo_id === governo_id);
  return NextResponse.json(items);
}
