"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import ModeToggle from "@/components/ModeToggle";

/** Nav principal (§8 redesigner) — enxuta. */
const PRIMARY_NAV: { href: string; label: string; soft?: boolean }[] = [
  { href: "/explorar", label: "Explorar" },
  { href: "/pessoas", label: "Pessoas" },
  { href: "/empresas", label: "Empresas" },
  { href: "/territorios", label: "Territórios" },
  { href: "/indicadores", label: "Indicadores" },
  { href: "/contas", label: "Contas" },
  { href: "/dinheiro", label: "Dinheiro" },
  { href: "/casos", label: "Justiça" },
  { href: "/investigacoes-beta", label: "Investigações" },
  { href: "/grafo", label: "Redes" },
  { href: "/fontes", label: "Fontes" },
];

/** Menu secundário — rotas úteis fora do eixo principal. */
const MORE_NAV = [
  { href: "/", label: "Início", exact: true },
  { href: "/mapas", label: "Mapas" },
  { href: "/magistrados", label: "Magistrados" },
  { href: "/historias", label: "Histórias" },
  { href: "/timeline", label: "Linha do tempo" },
  { href: "/grafo", label: "Grafo" },
  { href: "/instituicoes", label: "Instituições" },
  { href: "/investigacoes-beta", label: "Investigações" },
  { href: "/metodologia", label: "Metodologia" },
  { href: "/fontes#cobertura", label: "Cobertura" },
];

function isActive(pathname: string, href: string, exact?: boolean) {
  const path = href.split("#")[0];
  if (exact || path === "/") return pathname === "/";
  return pathname === path || pathname.startsWith(path + "/");
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/";
  const isHome = pathname === "/";
  const [q, setQ] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        const el = document.getElementById(
          "atlas-global-search"
        ) as HTMLInputElement | null;
        el?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  const moreActive = MORE_NAV.some((item) =>
    isActive(pathname, item.href, item.exact)
  );

  return (
    <div className={`atlas-shell${isHome ? " atlas-shell-home" : ""}`}>
      <header className="atlas-top">
        <Link href="/" className="atlas-brand">
          <span className="atlas-mark" aria-hidden>
            A
          </span>
          <span>
            ATLAS <em>BRASIL</em>
          </span>
        </Link>
        <form className="atlas-search" action="/explorar" method="get">
          <span aria-hidden>⌕</span>
          <input
            id="atlas-global-search"
            name="q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Pesquisar pessoa, empresa, partido, instituição, contrato, processo…"
            aria-label="Busca global"
          />
          <kbd>CTRL + K</kbd>
        </form>
        <div className="atlas-top-right">
          <Suspense fallback={null}>
            <ModeToggle />
          </Suspense>
          <Link href="/correcao" className="atlas-avatar" title="Correções">
            A
          </Link>
        </div>
      </header>
      <nav className="atlas-subnav" aria-label="Principal">
        {PRIMARY_NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={
              isActive(pathname, item.href)
                ? "active"
                : item.soft
                  ? "atlas-nav-soft"
                  : undefined
            }
          >
            {item.label}
          </Link>
        ))}
        <div className="atlas-nav-more">
          <button
            type="button"
            className={`atlas-nav-more-btn${moreActive || moreOpen ? " active" : ""}`}
            aria-expanded={moreOpen}
            aria-controls="atlas-nav-more-panel"
            onClick={() => setMoreOpen((v) => !v)}
          >
            Mais
          </button>
          {moreOpen ? (
            <div id="atlas-nav-more-panel" className="atlas-nav-more-panel" role="menu">
              {MORE_NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  role="menuitem"
                  className={
                    isActive(pathname, item.href, item.exact) ? "active" : undefined
                  }
                >
                  {item.label}
                </Link>
              ))}
            </div>
          ) : null}
        </div>
      </nav>
      <div className="atlas-body">{children}</div>
    </div>
  );
}
