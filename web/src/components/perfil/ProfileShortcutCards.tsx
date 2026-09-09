"use client";

import type { Entidade } from "@/lib/kb-types";
import { formatBRL } from "@/lib/format";
import type { ProfileTabId } from "./tabs";

type Card = {
  tab: ProfileTabId;
  title: string;
  value: string;
  hint?: string;
};

export default function ProfileShortcutCards({
  pessoa,
  qtdRelacoes,
  qtdCasos,
  qtdEmpresas,
  qtdDocs,
  onTab,
}: {
  pessoa: Entidade;
  qtdRelacoes: number;
  qtdCasos: number;
  qtdEmpresas: number;
  qtdDocs: number;
  onTab?: (tab: ProfileTabId) => void;
}) {
  const leg = pessoa.legislativo_resumo;
  const projetos = leg?.qtd_projetos ?? null;
  const propsTotal = leg?.qtd_proposicoes ?? 0;
  const cards: Card[] = [
    {
      tab: "mandatos",
      title: "Mandatos",
      value: pessoa.cargo_atual || "—",
      hint: pessoa.no_poder_2026
        ? "Em exercício"
        : "Fora de exercício neste corte",
    },
    {
      tab: "atuacao",
      title: "Atuação",
      value: String(projetos ?? leg?.votos_registrados ?? "—"),
      hint:
        projetos != null
          ? `${propsTotal} proposições · votos na amostra`
          : "Projetos e votações",
    },
    {
      tab: "dinheiro",
      title: "Dinheiro",
      value:
        pessoa.despesas_resumo?.total != null
          ? formatBRL(pessoa.despesas_resumo.total)
          : String(pessoa.emendas_resumo?.length ?? 0),
      hint:
        pessoa.despesas_resumo?.total != null
          ? "Cota / despesas (amostra)"
          : "Emendas na amostra",
    },
    {
      tab: "justica",
      title: "Justiça",
      value: String(qtdCasos),
      hint: "Menções documentais — não é culpa",
    },
    {
      tab: "relacoes",
      title: "Relações",
      value: String(qtdRelacoes),
      hint: qtdEmpresas ? `${qtdEmpresas} vínculo(s) empresa` : "Grafo documental",
    },
    {
      tab: "documentos",
      title: "Documentos",
      value: String(qtdDocs),
      hint: "Fontes do perfil",
    },
  ];

  return (
    <div className="profile-shortcuts">
      {cards.map((c) => (
        <button
          key={c.tab + c.title}
          type="button"
          className="profile-shortcut"
          onClick={() => onTab?.(c.tab)}
        >
          <span className="profile-shortcut-label">{c.title}</span>
          <strong className="profile-shortcut-value">{c.value}</strong>
          {c.hint ? <span className="faint">{c.hint}</span> : null}
        </button>
      ))}
    </div>
  );
}
