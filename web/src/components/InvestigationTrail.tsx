"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

type Step = { id: string; label: string };

export default function InvestigationTrail({
  suggestions,
}: {
  suggestions: Step[];
}) {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const initial = (sp.get("trilha") || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const [ids, setIds] = useState<string[]>(initial);

  const shareUrl = useMemo(() => {
    if (typeof window === "undefined") return "";
    const u = new URL(window.location.href);
    if (ids.length) u.searchParams.set("trilha", ids.join(","));
    else u.searchParams.delete("trilha");
    return u.toString();
  }, [ids]);

  function push(id: string, label: string) {
    if (ids.includes(id)) return;
    const next = [...ids, id];
    setIds(next);
    const params = new URLSearchParams(sp.toString());
    params.set("trilha", next.join(","));
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    void label;
  }

  function clear() {
    setIds([]);
    const params = new URLSearchParams(sp.toString());
    params.delete("trilha");
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(shareUrl || window.location.href);
      alert("Link da trilha copiado.");
    } catch {
      alert(shareUrl);
    }
  }

  const labelOf = (id: string) =>
    suggestions.find((s) => s.id === id)?.label || id;

  return (
    <div className="stack">
      <h2 className="section-title" style={{ fontSize: "1.15rem" }}>
        Minha investigação
      </h2>
      <p className="muted">
        Monte uma trilha e compartilhe o link. Path ≠ culpa.
      </p>
      <div className="chips">
        {suggestions.slice(0, 16).map((s) => (
          <button
            key={s.id}
            type="button"
            className="chip"
            onClick={() => push(s.id, s.label)}
          >
            + {s.label}
          </button>
        ))}
      </div>
      {ids.length === 0 ? (
        <p className="faint">Nenhum passo ainda.</p>
      ) : (
        <p className="muted" style={{ lineHeight: 1.8 }}>
          {ids.map((id, i) => (
            <span key={id}>
              {i > 0 ? " → " : ""}
              <Link href={`/grafo?centro=${id}`}>{labelOf(id)}</Link>
            </span>
          ))}
        </p>
      )}
      <div className="chips">
        <button type="button" className="btn" onClick={copy}>
          Copiar link
        </button>
        <button type="button" className="btn btn-ghost" onClick={clear}>
          Limpar
        </button>
        {ids.length >= 2 ? (
          <Link
            className="btn btn-ghost"
            href={`/grafo/conexao?a=${ids[0]}&b=${ids[ids.length - 1]}`}
          >
            Caminho do 1º ao último
          </Link>
        ) : null}
      </div>
    </div>
  );
}
