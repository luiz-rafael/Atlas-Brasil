import { NextRequest, NextResponse } from "next/server";
import { appendFileSync, mkdirSync } from "fs";
import path from "path";

export async function POST(req: NextRequest) {
  const body = await req.json();
  if (!body?.mensagem || String(body.mensagem).length < 10) {
    return NextResponse.json({ error: "mensagem curta" }, { status: 400 });
  }
  const dir = path.join(process.cwd(), "..", "data");
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, "correcoes.jsonl");
  appendFileSync(
    file,
    JSON.stringify({ ...body, at: new Date().toISOString() }) + "\n",
    "utf-8"
  );
  return NextResponse.json({ ok: true, storage: "file" });
}
