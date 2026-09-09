import { redirect } from "next/navigation";

/** /mapas → mapa de indicadores (AtlasMap). Presença KB antiga descontinuada. */
export default function MapasPage({
  searchParams,
}: {
  searchParams?: { ano?: string; ind?: string };
}) {
  const p = new URLSearchParams();
  p.set("ind", searchParams?.ind || "ind_pop_estimada");
  if (searchParams?.ano) p.set("ano", searchParams.ano);
  redirect(`/indicadores?${p.toString()}`);
}
