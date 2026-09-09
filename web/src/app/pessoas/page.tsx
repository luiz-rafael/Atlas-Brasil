import PessoasBrowser from "@/components/PessoasBrowser";
import { fetchPessoasList } from "@/lib/pessoas";
import { pessoas as pessoasKb } from "@/lib/kb";
import { foldAccents } from "@/lib/text-fold";
import type { PessoaListItem } from "@/lib/pessoas-types";

export default async function PessoasPage({
  searchParams,
}: {
  searchParams: { no_poder?: string; q?: string; escopo?: string; uf?: string };
}) {
  // Carrega o recorte (UF/escopo/poder) sem filtrar nome no servidor —
  // a busca por nome é live no cliente (acentos ignorados).
  const api = await fetchPessoasList({
    no_poder: searchParams.no_poder,
    escopo: searchParams.escopo,
    uf: searchParams.uf,
    limit: 2000,
  });

  let list: PessoaListItem[] = api?.items || [];
  let source = api?.source || "api";

  if (!api) {
    const kbList = pessoasKb({
      no_poder: searchParams.no_poder,
    });
    const escopo = searchParams.escopo?.toLowerCase();
    const ufN = (searchParams.uf || "").toUpperCase();
    const qFold = foldAccents(searchParams.q || "").trim();
    list = kbList
      .filter((p) => {
        if (ufN && (p.uf || "").toUpperCase() !== ufN) return false;
        if (qFold) {
          const blob = foldAccents(
            [p.nome, p.partido, p.cargo_atual, p.uf].map((x) => String(x || "")).join(" ")
          );
          const tokens = qFold.split(/\s+/).filter(Boolean);
          if (!tokens.every((t) => blob.includes(t))) return false;
        }
        if (!escopo) return true;
        const c = (p.cargo_atual || "").toLowerCase();
        if (escopo === "governadores") {
          return (
            c.includes("governador") ||
            p.tags?.some((t) => /governador|fase7/i.test(t)) ||
            (p.mandatos || []).some((m) =>
              String(m.cargo || "").toLowerCase().includes("governador")
            )
          );
        }
        return true;
      })
      .map((p) => ({
        id: p.id,
        nome: p.nome,
        partido: p.partido,
        cargo_atual: p.cargo_atual,
        uf: p.uf,
        foto_url: p.foto_url,
        no_poder_2026: p.no_poder_2026,
        despesas_resumo: p.despesas_resumo,
      }));
    source = "kb_fallback";
  }

  const escopoLabel =
    searchParams.escopo === "congresso"
      ? "Congresso"
      : searchParams.escopo === "presidencia"
        ? "Presidência / executivo"
        : searchParams.escopo === "governadores"
          ? "Governadores"
          : null;
  const ufLabel = searchParams.uf
    ? String(searchParams.uf).toUpperCase()
    : null;

  return (
    <div className="page stack">
      <div>
        <h1 className="section-title">
          Pessoas
          {escopoLabel ? ` · ${escopoLabel}` : ""}
          {ufLabel ? ` · ${ufLabel}` : ""}
        </h1>
        <p className="muted">
          Digite o nome e a lista filtra na hora — acentos não importam (José =
          jose).
        </p>
      </div>
      <PessoasBrowser
        items={list}
        source={source}
        initialQ={searchParams.q || ""}
        uf={searchParams.uf || ""}
        no_poder={searchParams.no_poder || ""}
        escopo={searchParams.escopo || ""}
      />
    </div>
  );
}
