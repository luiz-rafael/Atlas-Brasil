import Link from "next/link";
import type { Administration } from "@/lib/administrations";

/**
 * AtlasGovernmentContext — painel do governo vigente no território/ano.
 * Não atribui causalidade a indicadores.
 */
export default function AtlasGovernmentContext({
  year,
  administration,
  territoryLabel,
}: {
  year: number;
  administration: Administration | null | undefined;
  territoryLabel?: string;
}) {
  if (!administration) {
    return (
      <div className="panel stack">
        <p className="eyebrow">Contexto de governo · {year}</p>
        <p className="muted">
          Sem administração estadual documentada para{" "}
          {territoryLabel || "este território"} em {year}.
        </p>
        <p className="prose-note">
          Fonte atual: mandatos de governador (TSE). Ausência ≠ inexistência
          histórica — pode ser lacuna de cobertura.
        </p>
      </div>
    );
  }

  const personId = administration.executive_person_id;
  const name =
    administration.executive_person_name || personId || "Titular não resolvido";

  return (
    <div className="panel stack">
      <p className="eyebrow">
        Administração vigente · {year}
        {territoryLabel ? ` · ${territoryLabel}` : ""}
      </p>
      <p className="item-title">{name}</p>
      <p className="item-meta">
        {[administration.party_at_start, administration.administration_type]
          .filter(Boolean)
          .join(" · ")}
        {administration.start_date
          ? ` · ${administration.start_date} → ${administration.end_date || "…"}`
          : ""}
      </p>
      <p className="prose-note">
        Indicadores do período são observações territoriais — não efeitos
        atribuídos automaticamente ao titular.
      </p>
      <div className="chips">
        {personId ? (
          <Link className="chip" href={`/pessoas/${personId}`}>
            Perfil da pessoa
          </Link>
        ) : null}
        {administration.administration_id ? (
          <span className="chip faint">{administration.administration_id}</span>
        ) : null}
      </div>
    </div>
  );
}
