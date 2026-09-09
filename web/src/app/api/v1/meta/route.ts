import { NextResponse } from "next/server";
import { getKB } from "@/lib/kb";

export async function GET() {
  return NextResponse.json(getKB().meta);
}
