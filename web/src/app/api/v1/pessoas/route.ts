import { NextRequest, NextResponse } from "next/server";
import { pessoas } from "@/lib/kb";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  return NextResponse.json(
    pessoas({
      q: sp.get("q") || undefined,
      partido: sp.get("partido") || undefined,
      no_poder: sp.get("no_poder") || undefined,
      tag: sp.get("tag") || undefined,
    })
  );
}
