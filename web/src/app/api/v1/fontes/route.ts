import { NextRequest, NextResponse } from "next/server";
import { documentos } from "@/lib/kb";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  return NextResponse.json(
    documentos({
      nivel: sp.get("nivel") || undefined,
      orgao: sp.get("orgao") || undefined,
      caso_id: sp.get("caso_id") || undefined,
    })
  );
}
