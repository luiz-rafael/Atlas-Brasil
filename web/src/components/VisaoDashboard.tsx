"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import BrazilTerritoryMap from "@/components/BrazilTerritoryMap";

type Props = {
  stats: {
    pessoas: number;
    empresas: number;
    docs: number;
    rels: number;
    casos: number;
    instituicoes: number;
    crime: number;
    versao: string;
    contratos?: number;
    comBens?: number;
  };
  coverage?: {
    total: number;
    active: number;
    ingested: number;
    porStatus: Record<string, number>;
  } | null;
  kb: {
    entidades: Array<{
      id: string;
      tipo: string;
      uf?: string | null;
      isolada?: boolean;
      tags?: string[];
      nome?: string;
      cargo_atual?: string | null;
    }>;
    relacoes: Array<{ origem: string; destino: string; tipo?: string }>;
  };
  updates: Array<{ title: string; when: string; href: string }>;
};

export default function VisaoDashboard({ stats, kb, updates, coverage }: Props) {
  const [theme, setTheme] = useState<string | null>(null);

  const themes = useMemo(
    () => [
      {
        id: "politica",
        nome: "Política",
        n: stats.pessoas,
        color: "var(--cat-politica)",
        href: "/pessoas",
      },
      {
        id: "empresas",
        nome: "Empresas",
        n: stats.empresas,
        color: "var(--cat-empresas)",
        href: "/empresas",
      },
      {
        id: "crime",
        nome: "Crime organizado",
        n: stats.crime,
        color: "var(--cat-crime)",
        href: "/crime",
      },
      {
        id: "instituicoes",
        nome: "Instituições",
        n: stats.instituicoes,
        color: "var(--cat-instituicoes)",
        href: "/instituicoes",
      },
      {
        id: "casos",
        nome: "Processos / casos",
        n: stats.casos,
        color: "var(--violet)",
        href: "/casos",
      },
      {
        id: "docs",
        nome: "Documentos",
        n: stats.docs,
        color: "var(--cyan)",
        href: "/fontes",
      },
    ],
    [stats]
  );

  const maxTheme = Math.max(1, ...themes.map((t) => t.n));
  const [now, setNow] = useState("—");
  useEffect(() => {
    setNow(
      new Date().toLocaleString("pt-BR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    );
  }, []);

  return (
    <div className="dash-grid" style={{ animation: "rise 0.45s ease both" }}>
      <div className="dash-head">
        <div>
          <h1 className="section-title">Visão Geral</h1>
          <p className="muted">
            Panorama integrado das redes de poder, dinheiro, instituições e crime
            no Brasil · KB {stats.versao}
          </p>
        </div>
        <p className="faint">Última atualização: {now}</p>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <span className="label">Pessoas</span>
          <span className="value">{stats.pessoas.toLocaleString("pt-BR")}</span>
          <span className="delta">no grafo documental</span>
        </div>
        <div className="stat-card">
          <span className="label">Empresas</span>
          <span className="value">{stats.empresas.toLocaleString("pt-BR")}</span>
          <span className="delta">com arestas/fonte</span>
        </div>
        <div className="stat-card">
          <span className="label">Contratos PNCP</span>
          <span className="value">
            {(stats.contratos ?? 0).toLocaleString("pt-BR")}
          </span>
          <span className="delta">
            <Link href="/dinheiro">ver dinheiro</Link>
          </span>
        </div>
        <div className="stat-card">
          <span className="label">Relações</span>
          <span className="value">{stats.rels.toLocaleString("pt-BR")}</span>
          <span className="delta">path ≠ culpa</span>
        </div>
      </div>

      {coverage ? (
        <section className="panel" style={{ marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1rem", margin: 0 }}>Cobertura das fontes</h2>
          <p className="muted" style={{ margin: "0.35rem 0 0.75rem" }}>
            {coverage.total} fontes no registry · {coverage.active} active ·{" "}
            {coverage.ingested} com ingestão recente
            {stats.comBens
              ? ` · ${stats.comBens.toLocaleString("pt-BR")} perfis com bens TSE`
              : ""}
          </p>
          <div className="chips">
            {Object.entries(coverage.porStatus).map(([k, v]) => (
              <span key={k} className="chip">
                {k}: {v}
              </span>
            ))}
            <Link className="chip" href="/status">
              Status detalhado →
            </Link>
          </div>
        </section>
      ) : null}

      <div className="dash-split dash-split-3">
        <aside className="panel">
          <h2>Principais temas</h2>
          {themes.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`theme-row theme-btn ${theme === t.id ? "active" : ""}`}
              onClick={() => setTheme(theme === t.id ? null : t.id)}
            >
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>{t.nome}</span>
                  <span className="faint">{t.n.toLocaleString("pt-BR")}</span>
                </div>
                <div className="bar">
                  <i
                    style={{
                      width: `${Math.round((t.n / maxTheme) * 100)}%`,
                      background: t.color,
                    }}
                  />
                </div>
              </div>
            </button>
          ))}
          <p className="faint" style={{ marginTop: 12 }}>
            Clique um tema para filtrar o mapa ·{" "}
            <Link href="/mapas" style={{ color: "var(--cyan)" }}>
              mapa completo
            </Link>
          </p>
          <div className="chips" style={{ marginTop: 8 }}>
            {themes.map((t) => (
              <Link key={t.id} className="chip" href={t.href}>
                Abrir {t.nome.split(" ")[0]}
              </Link>
            ))}
          </div>
        </aside>

        <div className="map-stage map-stage-grow">
          <BrazilTerritoryMap
            kb={kb}
            compact
            showLegend
            themeFilter={theme}
          />
        </div>
      </div>

      <div>
        <h2 className="section-title" style={{ fontSize: "1rem" }}>
          Atualizações recentes
        </h2>
        <div className="updates-rail">
          {updates.map((u) => (
            <Link key={u.title} className="update-chip" href={u.href}>
              <strong style={{ color: "var(--ink)" }}>{u.title}</strong>
              <span className="faint"> · {u.when}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
