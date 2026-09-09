export type PessoaListItem = {
  id: string;
  nome: string;
  tipo?: string;
  partido?: string | null;
  cargo_atual?: string | null;
  uf?: string | null;
  foto_url?: string | null;
  no_poder_2026?: boolean;
  tags?: string[];
  despesas_resumo?: { total?: number; ano?: number } | null;
  registros_count?: number;
  status_badge?: string;
};
