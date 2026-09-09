import { NextResponse } from "next/server";
import {
  entityById,
  registrosDePessoa,
  relacoesDe,
} from "@/lib/kb";

export async function GET(
  _req: Request,
  { params }: { params: { id: string } }
) {
  const pessoa = entityById(params.id);
  if (!pessoa) return NextResponse.json({ error: "not_found" }, { status: 404 });
  return NextResponse.json({
    ...pessoa,
    registros: registrosDePessoa(params.id),
    relacoes: relacoesDe(params.id),
  });
}
