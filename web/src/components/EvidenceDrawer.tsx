"use client";

import { useEffect, useState } from "react";

export type EvidenceItem = {
  id?: string;
  titulo?: string;
  fonte?: string;
  url?: string;
  score?: number;
  trecho?: string;
  grau?: string;
};

/**
 * Evidence drawer — fontes/documentos ligados ao contexto atual.
 * Não implica culpa.
 */
export default function EvidenceDrawer({
  title = "Evidências",
  items,
  open: openProp,
}: {
  title?: string;
  items: EvidenceItem[];
  open?: boolean;
}) {
  const [open, setOpen] = useState(Boolean(openProp));
  useEffect(() => {
    if (openProp != null) setOpen(openProp);
  }, [openProp]);

  if (!items?.length) return null;

  return (
    <div className="evidence-drawer">
      <button
        type="button"
        className="btn-outline"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "Ocultar" : "Ver"} {title} ({items.length})
      </button>
      {open ? (
        <aside className="panel stack" style={{ marginTop: "0.75rem" }}>
          <p className="prose-note">
            Documentos e trechos indexados. Fonte ≠ veredito. Processo ≠ culpa.
          </p>
          <div className="list-block">
            {items.map((e, i) => (
              <div key={e.id || i} className="list-item">
                <span className="item-title">{e.titulo || e.id || "—"}</span>
                <span className="item-meta">
                  {[e.fonte, e.grau, e.score != null ? `score ${e.score.toFixed?.(2) ?? e.score}` : null]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {e.trecho ? <p className="muted">{e.trecho}</p> : null}
                {e.url ? (
                  <a href={e.url} target="_blank" rel="noreferrer">
                    Abrir fonte
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        </aside>
      ) : null}
    </div>
  );
}
