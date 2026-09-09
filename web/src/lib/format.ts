/** Helpers de formatação seguros para Client e Server Components. */

export function formatReais(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (abs >= 1e12) return `${sign}R$ ${(abs / 1e12).toFixed(2)} tri`;
  if (abs >= 1e9) return `${sign}R$ ${(abs / 1e9).toFixed(2)} bi`;
  if (abs >= 1e6) return `${sign}R$ ${(abs / 1e6).toFixed(1)} mi`;
  if (abs >= 1e3) {
    return `${sign}R$ ${abs.toLocaleString("pt-BR", {
      maximumFractionDigits: 0,
    })}`;
  }
  return `${sign}R$ ${abs.toLocaleString("pt-BR", {
    minimumFractionDigits: abs < 1 && abs > 0 ? 2 : 0,
    maximumFractionDigits: 2,
  })}`;
}

/** Valor exato em R$ (sem abreviar) — útil em title/tooltip. */
export function formatReaisExact(n: number): string {
  return n.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 2,
  });
}

/**
 * Dinheiro para UI: mi/bi/tri acima de 1 milhão.
 * Evita "R$ 8.587.445.462.373" ilegível.
 */
export function formatBRL(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return formatReais(Number(n));
}

/** Converte unidades Contas (BRL_millions, BRL_units, ratio…) para exibição. */
export function formatContasValue(
  value: number | null | undefined,
  unit?: string | null
): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  const u = (unit || "").trim();

  if (u === "ratio" || u === "pct_pib" || u === "%_pib") {
    const pct = Math.abs(n) <= 1.5 ? n * 100 : n;
    return `${pct.toLocaleString("pt-BR", {
      maximumFractionDigits: 1,
      minimumFractionDigits: 1,
    })}% do PIB`;
  }
  if (u === "%" || u === "percent" || u === "pct") {
    const pct = Math.abs(n) <= 1.5 ? n * 100 : n;
    return `${pct.toLocaleString("pt-BR", {
      maximumFractionDigits: 1,
    })}%`;
  }

  let reais = n;
  if (
    u === "BRL_millions" ||
    u === "R$_mi" ||
    u === "mi" ||
    u === "R$ mi" ||
    u.toLowerCase() === "brl_millions"
  ) {
    reais = n * 1_000_000;
  } else if (u === "BRL_thousands" || u === "R$_mil") {
    reais = n * 1_000;
  }
  // BRL, BRL_units, R$ → já em reais
  return formatReais(reais);
}

export function formatContasExact(
  value: number | null | undefined,
  unit?: string | null
): string | null {
  if (value == null || Number.isNaN(Number(value))) return null;
  const n = Number(value);
  const u = (unit || "").trim();
  if (u === "ratio" || u === "pct_pib" || u === "%_pib") {
    const pct = Math.abs(n) <= 1.5 ? n * 100 : n;
    return `${pct.toLocaleString("pt-BR", {
      maximumFractionDigits: 4,
    })}% do PIB`;
  }
  let reais = n;
  if (u === "BRL_millions" || u === "R$_mi" || u === "mi") {
    reais = n * 1_000_000;
  } else if (u === "BRL_thousands" || u === "R$_mil") {
    reais = n * 1_000;
  }
  return formatReaisExact(reais);
}

export const STATUS_LABEL: Record<string, string> = {
  condenado: "Condenado",
  reu: "Réu",
  indiciado: "Indiciado",
  investigado: "Investigado",
  citado: "Citado / mencionado",
  absolvido: "Absolvido / arquivado",
  controversia: "Controvérsia política",
};

export function formatPop(n: number): string {
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

/** PIB SIDRA vem em mil reais; exibe em R$ (reais). */
export function formatPibMilReais(milReais: number): string {
  return formatReais(milReais * 1000);
}

export function formatIndicatorValue(
  indicatorId: string,
  value: number
): string {
  if (indicatorId === "ind_pib_corrente") return formatPibMilReais(value);
  if (indicatorId === "ind_pib_per_capita") {
    return `R$ ${value.toLocaleString("pt-BR", {
      maximumFractionDigits: 0,
    })}/hab`;
  }
  if (indicatorId.startsWith("ind_ideb_")) {
    return value.toLocaleString("pt-BR", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
  }
  if (indicatorId === "ind_mortalidade_infantil") {
    return value.toLocaleString("pt-BR", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
  }
  if (
    indicatorId === "ind_mortalidade_geral" ||
    indicatorId === "ind_natalidade" ||
    indicatorId === "ind_homicidios_per_100k" ||
    indicatorId === "ind_cvli_per_100k"
  ) {
    return value.toLocaleString("pt-BR", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
  }
  if (
    indicatorId === "ind_nascidos_vivos" ||
    indicatorId === "ind_obitos" ||
    indicatorId === "ind_obitos_infantis" ||
    indicatorId === "ind_homicidios" ||
    indicatorId === "ind_mortes_causas_externas"
  ) {
    return formatPop(value);
  }
  if (
    indicatorId.endsWith("_per_capita") &&
    indicatorId.startsWith("ind_despesa")
  ) {
    return `${formatReais(value)}/hab`;
  }
  if (
    indicatorId === "ind_investimento_per_capita" ||
    indicatorId === "ind_despesa_saude_per_capita" ||
    indicatorId === "ind_despesa_educacao_per_capita" ||
    indicatorId === "ind_despesa_pessoal_per_capita"
  ) {
    return `${formatReais(value)}/hab`;
  }
  if (
    indicatorId.startsWith("ind_receita_") ||
    indicatorId.startsWith("ind_despesa_") ||
    indicatorId === "ind_rcl" ||
    indicatorId === "ind_transferencias_correntes" ||
    indicatorId === "ind_renuncia_fiscal"
  ) {
    return formatReais(value);
  }
  return formatPop(value);
}

export function formatSignedPercent(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toLocaleString("pt-BR", {
    maximumFractionDigits: 1,
    minimumFractionDigits: pct === 0 ? 0 : 1,
  })}%`;
}

export function formatVariation(
  current: number | null | undefined,
  previous: number | null | undefined
): { label: string; direction: "up" | "down" | "flat"; pct: number } | null {
  if (current == null || previous == null || previous === 0) return null;
  const pct = ((current - previous) / Math.abs(previous)) * 100;
  if (!Number.isFinite(pct)) return null;
  if (Math.abs(pct) < 0.05) {
    return { label: "estável", direction: "flat", pct: 0 };
  }
  return {
    label: formatSignedPercent(pct),
    direction: pct > 0 ? "up" : "down",
    pct,
  };
}

export function variationTone(
  direction: "up" | "down" | "flat",
  higherIsBetter: boolean
): "good" | "bad" | "neutral" {
  if (direction === "flat") return "neutral";
  const improved =
    (higherIsBetter && direction === "up") ||
    (!higherIsBetter && direction === "down");
  return improved ? "good" : "bad";
}
