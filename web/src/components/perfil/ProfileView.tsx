"use client";

import { useCallback, useState } from "react";
import type { Entidade, Relacao, Registro, Caso } from "@/lib/kb-types";
import ProfileHeader from "./ProfileHeader";
import ProfileTabs from "./ProfileTabs";
import ProfilePanels from "./ProfilePanels";
import { parseProfileTab, tabHref, type ProfileTabId } from "./tabs";
import type { GEdge, GNode } from "@/components/InteractiveGraph";

export default function ProfileView({
  initialTab,
  pessoa,
  rels,
  regs,
  casos,
  labels,
  fontes,
  graphNodes,
  graphEdges,
}: {
  initialTab: ProfileTabId;
  pessoa: Entidade;
  rels: Relacao[];
  regs: Registro[];
  casos: Record<string, Pick<Caso, "id" | "nome">>;
  labels: Record<string, string>;
  fontes: string[];
  graphNodes: GNode[];
  graphEdges: Array<
    GEdge & { justificativa_documental?: string; contexto?: string; periodo?: string }
  >;
}) {
  const [tab, setTab] = useState<ProfileTabId>(initialTab);

  const onTab = useCallback(
    (next: ProfileTabId) => {
      setTab(next);
      const href = tabHref(pessoa.id, next);
      if (typeof window !== "undefined") {
        window.history.replaceState(null, "", href);
      }
    },
    [pessoa.id],
  );

  return (
    <div className="stack profile-page" style={{ animation: "rise 0.45s ease both" }}>
      <ProfileHeader pessoa={pessoa} onTab={onTab} />
      <ProfileTabs pessoaId={pessoa.id} active={tab} onChange={onTab} />
      <ProfilePanels
        tab={tab}
        pessoa={pessoa}
        rels={rels}
        regs={regs}
        casos={casos}
        labels={labels}
        fontes={fontes}
        graphNodes={graphNodes}
        graphEdges={graphEdges}
        onTab={onTab}
      />
    </div>
  );
}

export function coerceInitialTab(raw?: string | null): ProfileTabId {
  return parseProfileTab(raw);
}
