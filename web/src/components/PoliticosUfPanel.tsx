"use client";

import Link from "next/link";
import {
  POLITICO_CLASSE_LABEL,
  TIP_CLASSES,
  type PoliticosUfSummary,
} from "@/lib/politicos-by-uf";

export default function PoliticosUfPanel({
  uf,
  ufNome,
  summary,
  compact,
}: {
  uf: string;
  ufNome?: string;
  summary?: PoliticosUfSummary | null;
  compact?: boolean;
}) {
  const total = summary?.total ?? 0;
  const byClass = summary?.byClass || {};
  const sample = summary?.sample || [];
  const nome = ufNome || uf;

  return (
    <div className={`atlas-politicos-panel${compact ? " compact" : ""}`}>
      <p className="eyebrow">Políticos deste estado</p>
      <h3 className="atlas-politicos-title">
        {nome}
        {total ? (
          <span className="faint"> · {total} em exercício (amostra Atlas)</span>
        ) : null}
      </h3>
      <p className="prose-note">
        Contagens no corte Atlas: governador(a), senadores e deputados
        federais eleitos por este UF. Ainda não há coleta de Assembleia
        Legislativa, prefeituras ou câmaras municipais.
      </p>
      {total ? (
        <ul className="atlas-politicos-counts">
          {TIP_CLASSES.map((c) => {
            const n = byClass[c];
            if (!n) return null;
            return (
              <li key={c}>
                <span>{POLITICO_CLASSE_LABEL[c]}</span>
                <strong>{n}</strong>
              </li>
            );
          })}
          {byClass.outro ? (
            <li>
              <span>{POLITICO_CLASSE_LABEL.outro}</span>
              <strong>{byClass.outro}</strong>
            </li>
          ) : null}
        </ul>
      ) : (
        <p className="muted">Sem políticos deste UF no corte atual.</p>
      )}
      {sample.length ? (
        <div className="list-block atlas-politicos-sample">
          {sample.map((p) => (
            <Link key={p.id} href={`/pessoas/${p.id}`} className="list-item">
              <p className="item-title">{p.nome}</p>
              <p className="item-meta">
                {[
                  POLITICO_CLASSE_LABEL[p.classe],
                  p.partido,
                  p.cargo_atual,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </Link>
          ))}
        </div>
      ) : null}
      <div className="chips">
        <Link
          className="chip"
          href={`/pessoas?no_poder=sim&uf=${encodeURIComponent(uf)}`}
        >
          Ver todos de {uf}
        </Link>
        <Link className="chip" href={`/territorios/${uf}`}>
          Território {uf}
        </Link>
      </div>
    </div>
  );
}
