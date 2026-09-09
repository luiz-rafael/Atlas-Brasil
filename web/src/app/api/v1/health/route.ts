import { NextResponse } from "next/server";
import { getKB } from "@/lib/kb";

export async function GET() {
  const kb = getKB();
  return NextResponse.json({
    ok: true,
    produto: "ATLAS BRASIL",
    versao_kb: kb.meta?.versao,
    entidades: kb.entidades.length,
    casos: kb.casos.length,
    relacoes: kb.relacoes.length,
  });
}
