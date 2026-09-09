"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { formatBRL, STATUS_LABEL } from "@/lib/format";
import { foldAccents, matchesFolded } from "@/lib/text-fold";
import type { PessoaListItem } from "@/lib/pessoas-types";

type Props = {
  items: PessoaListItem[];
  source: string;
  initialQ?: string;
  uf?: string;
  no_poder?: string;
  escopo?: string;
};

export default function PessoasBrowser({
  items,
  source,
  initialQ = "",
  uf = "",
  no_poder = "",
  escopo = "",
}: Props) {
  const router = useRouter();
  const [q, setQ] = useState(initialQ);

  // URL compartilhável sem remount (evita perder o foco do input).
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams();
      const qq = q.trim();
      if (qq) p.set("q", qq);
      if (uf) p.set("uf", uf);
      if (no_poder) p.set("no_poder", no_poder);
      if (escopo) p.set("escopo", escopo);
      const qs = p.toString();
      const href = qs ? `/pessoas?${qs}` : "/pessoas";
      if (typeof window !== "undefined") {
        const cur = window.location.pathname + window.location.search;
        if (cur !== href) window.history.replaceState(null, "", href);
      }
    }, 200);
    return () => clearTimeout(t);
  }, [q, uf, no_poder, escopo]);

  const filtered = useMemo(() => {
    const needle = foldAccents(q).trim();
    if (!needle) return items;
    const tokens = needle.split(/\s+/).filter(Boolean);
    return items.filter((p) => {
      const blob = [p.nome, p.partido, p.cargo_atual, p.uf]
        .map((x) => String(x || ""))
        .join(" ");
      return tokens.every((tok) => matchesFolded(blob, tok));
    });
  }, [items, q]);

  return (
    <div className="stack">
      <form
        className="filters"
        method="get"
        onSubmit={(e) => {
          e.preventDefault();
          const fd = new FormData(e.currentTarget);
          const p = new URLSearchParams();
          const qq = String(fd.get("q") || q || "").trim();
          const u = String(fd.get("uf") || "").trim().toUpperCase();
          const np = String(fd.get("no_poder") || "");
          const esc = String(fd.get("escopo") || "");
          if (qq) p.set("q", qq);
          if (u) p.set("uf", u);
          if (np) p.set("no_poder", np);
          if (esc) p.set("escopo", esc);
          router.push(p.toString() ? `/pessoas?${p}` : "/pessoas");
        }}
      >
        <input
          name="q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar nome (ao digitar · ignora acentos)…"
          autoComplete="off"
          autoFocus
          aria-label="Buscar pessoas por nome"
        />
        <input
          name="uf"
          defaultValue={uf}
          placeholder="UF"
          maxLength={2}
          style={{ width: 64, textTransform: "uppercase" }}
        />
        <select name="no_poder" defaultValue={no_poder}>
          <option value="">Poder 2026: todos</option>
          <option value="sim">Com cargo atual</option>
          <option value="nao">Fora do poder</option>
        </select>
        <select name="escopo" defaultValue={escopo}>
          <option value="">Escopo: todos</option>
          <option value="congresso">Congresso</option>
          <option value="governadores">Governadores</option>
          <option value="presidencia">Presidência / executivo / STF</option>
          <option value="stf">STF</option>
        </select>
        <button className="btn" type="submit">
          Aplicar filtros
        </button>
      </form>

      <p className="faint">
        Fonte: {source} · {filtered.length}
        {filtered.length !== items.length ? ` de ${items.length}` : ""} pessoa(s)
        {q.trim() ? ` · “${q.trim()}”` : ""}
      </p>

      <div className="list-block">
        {filtered.map((p) => {
          const initials = p.nome
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((w) => w[0])
            .join("")
            .toUpperCase();
          return (
            <Link
              key={p.id}
              href={`/pessoas/${p.id}`}
              className="list-item list-item-person"
            >
              {p.foto_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  className="avatar-sm"
                  src={p.foto_url}
                  alt=""
                  width={40}
                  height={40}
                  referrerPolicy="no-referrer"
                />
              ) : (
                <span className="avatar-sm avatar-sm-fallback" aria-hidden>
                  {initials}
                </span>
              )}
              <span style={{ flex: 1, minWidth: 0 }}>
                <span className="item-title">{p.nome}</span>
                <span className="item-meta">
                  {p.partido || "—"} · {p.cargo_atual || "Sem cargo informado"}
                  {p.uf ? ` · ${p.uf}` : ""}
                  {p.no_poder_2026 ? " · no poder" : ""}
                  {p.despesas_resumo?.total != null
                    ? ` · cota ${p.despesas_resumo.ano}: ${formatBRL(
                        p.despesas_resumo.total
                      )}`
                    : ""}
                  {p.status_badge ? (
                    <>
                      {" · "}
                      <span className={`badge badge-${p.status_badge}`}>
                        {STATUS_LABEL[p.status_badge] || p.status_badge}
                      </span>
                    </>
                  ) : null}
                </span>
              </span>
            </Link>
          );
        })}
      </div>
      {!filtered.length ? (
        <p className="muted">Nenhuma pessoa neste filtro.</p>
      ) : null}
    </div>
  );
}
