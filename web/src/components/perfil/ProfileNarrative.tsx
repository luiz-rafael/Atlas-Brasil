import type { Entidade } from "@/lib/kb-types";
import { formatBRL } from "@/lib/format";

/** Narrativa automática só com fatos — sem juízo. */
export default function ProfileNarrative({
  pessoa,
  qtdRelacoes,
  qtdCasos,
}: {
  pessoa: Entidade;
  qtdRelacoes: number;
  qtdCasos: number;
}) {
  const parts: string[] = [];
  const leg = pessoa.legislativo_resumo;

  parts.push(
    `${pessoa.nome}${pessoa.partido ? `, filiado(a) ao ${pessoa.partido}` : ""}${
      pessoa.uf ? ` (${pessoa.uf})` : ""
    }.`
  );

  if (pessoa.cargo_atual) {
    parts.push(`Cargo registrado neste corte: ${pessoa.cargo_atual}.`);
  }

  if (pessoa.no_poder_2026) {
    parts.push("Em exercício no recorte atual da base.");
  } else {
    parts.push("Não consta como em exercício na lista atual da Casa.");
  }

  if (leg?.anos_atividade != null && leg.ano_inicio_atividade) {
    parts.push(
      `Atividade legislativa na amostra de ${leg.ano_inicio_atividade} a ${
        leg.ano_fim_atividade ?? "—"
      } (~${leg.anos_atividade} ano(s)).`
    );
  }

  if (leg) {
    const bits: string[] = [];
    if (leg.qtd_projetos != null) {
      bits.push(
        `${leg.qtd_projetos} projeto(s) (PL/PEC/PLP etc.)`
      );
    }
    if (leg.qtd_proposicoes != null) {
      bits.push(
        `${leg.qtd_proposicoes} proposição(ões) no total (inclui requerimentos e outros tipos)`
      );
    }
    if (leg.votos_registrados != null || leg.votacoes_nominais != null) {
      bits.push(
        `${leg.votos_registrados ?? leg.votacoes_nominais} voto(s) nominal(is) registrado(s) na amostra`
      );
    }
    if (bits.length) parts.push(`Atividade legislativa: ${bits.join("; ")}.`);
  }

  if (pessoa.emendas_resumo?.length) {
    const total = pessoa.emendas_resumo.reduce(
      (a, e) => a + (e.valor || 0),
      0
    );
    parts.push(
      `${pessoa.emendas_resumo.length} emenda(s) vinculadas ao autor nesta amostra` +
        (total ? ` (soma indicativa ${formatBRL(total)})` : "") +
        "."
    );
  }

  if (pessoa.despesas_resumo?.total != null) {
    parts.push(
      `Cota parlamentar ${pessoa.despesas_resumo.ano ?? ""}: ${formatBRL(
        pessoa.despesas_resumo.total
      )} liquidado na amostra.`
    );
  }

  if (pessoa.bens_declarados?.valor_total != null) {
    parts.push(
      `Bens declarados (TSE): ${formatBRL(pessoa.bens_declarados.valor_total)}` +
        (pessoa.bens_declarados.qtd
          ? ` em ${pessoa.bens_declarados.qtd} item(ns)`
          : "") +
        "."
    );
  }

  parts.push(
    `Nesta base: ${qtdRelacoes} relação(ões) documentada(s)` +
      (qtdCasos
        ? ` e ${qtdCasos} registro(s) pessoa–caso`
        : " e nenhum registro pessoa–caso") +
      "."
  );

  return (
    <section className="profile-narrative surface-paper stack">
      <h2>Em uma frase</h2>
      <p>{parts.join(" ")}</p>
      <p className="prose-note">
        Texto gerado só a partir dos campos da base. Não é opinião nem acusação.
        Frequência/presença em plenário só entra quando houver coleta da fonte
        oficial da Câmara.
      </p>
    </section>
  );
}
