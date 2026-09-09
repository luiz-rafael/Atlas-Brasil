import { NextResponse } from "next/server";
import { getKB } from "@/lib/kb";

export async function GET() {
  const kb = getKB();
  return NextResponse.json({
    centrao: kb.dossie_centrao,
    poder_2026: kb.mapa_poder_2026,
    governos: kb.governos,
  });
}
