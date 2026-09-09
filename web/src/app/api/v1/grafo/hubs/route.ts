import { NextRequest, NextResponse } from "next/server";
import {
  hubsByPeriod,
  hubsRanking,
  type MetricName,
} from "@/lib/network-metrics";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const metric = (sp.get("metric") || "degree") as MetricName;
  const tipo = sp.get("tipo") || "todos";
  const de = sp.get("de") || undefined;
  const ate = sp.get("ate") || undefined;
  const porPeriodo = sp.get("por_periodo") === "1";
  const graus = sp.get("graus")?.split(",").filter(Boolean);

  if (porPeriodo) {
    return NextResponse.json(hubsByPeriod(metric));
  }

  return NextResponse.json(
    hubsRanking(metric, { tipo, de, ate, graus, limit: 30 })
  );
}
