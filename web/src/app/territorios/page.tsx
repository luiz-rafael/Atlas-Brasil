import Link from "next/link";
import { BR_STATE_PATHS } from "@/lib/br-states-paths";
import {
  BR_REGION_ORDER,
  BR_UF_CAPITAL,
  BR_UF_REGION,
} from "@/lib/br-uf-meta";

export default function TerritoriosIndexPage() {
  const byRegion = BR_REGION_ORDER.map((region) => ({
    region,
    states: BR_STATE_PATHS.filter((s) => BR_UF_REGION[s.uf] === region).sort(
      (a, b) => a.nome.localeCompare(b.nome, "pt-BR")
    ),
  }));

  return (
    <div className="page atlas-territory-index">
      <header className="atlas-territory-index-head">
        <p className="eyebrow">Brasil · estados</p>
        <h1 className="atlas-territory-title">Territórios</h1>
        <p className="atlas-territory-lede">
          Escolha um estado para ver população, economia, indicadores sociais e
          quem governava em cada período — observação, não causalidade.
        </p>
      </header>

      <div className="atlas-territory-regions">
        {byRegion.map(({ region, states }) => (
          <section key={region} className="atlas-territory-region">
            <h2>{region}</h2>
            <div className="atlas-territory-grid">
              {states.map((s) => (
                <Link
                  key={s.uf}
                  href={`/territorios/${s.uf}`}
                  className="atlas-territory-card"
                >
                  <strong>
                    {s.nome} <span>{s.uf}</span>
                  </strong>
                  <em>{BR_UF_CAPITAL[s.uf] || "—"}</em>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
