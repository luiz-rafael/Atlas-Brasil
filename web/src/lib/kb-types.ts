/**
 * Tipos da KB seguros para Client Components.
 * A implementação com JSON fica em kb.ts (server-only).
 */

export type Entidade = {
  id: string;
  tipo: string;
  nome: string;
  partido?: string | null;
  cargo_atual?: string | null;
  mandatos?: Array<{
    id?: string;
    cargo?: string | null;
    uf?: string | null;
    partido?: string | null;
    ano_eleicao?: number | null;
    inicio?: string | null;
    fim?: string | null;
    fonte?: string;
  }> | null;
  no_poder_2026?: boolean;
  situacao_casa?: string | null;
  uf?: string | null;
  tags?: string[];
  aliases?: string[];
  isolada?: boolean;
  nota?: string;
  foto_url?: string | null;
  email?: string | null;
  nome_civil?: string | null;
  data_nascimento?: string | null;
  escolaridade?: string | null;
  municipio_nascimento?: string | null;
  uf_nascimento?: string | null;
  redes_sociais?: string[];
  gabinete?: {
    nome?: string | null;
    predio?: string | null;
    sala?: string | null;
    telefone?: string | null;
    email?: string | null;
  } | null;
  pagina_oficial?: string | null;
  despesas_resumo?: {
    ano?: number;
    total?: number;
    qtd_lancamentos?: number;
    por_tipo?: Array<{ tipo: string; valor: number }>;
    fornecedores?: Array<{
      cnpj?: string | null;
      nome?: string | null;
      valor?: number;
      qtd?: number;
    }>;
    fonte_url?: string;
    fonte?: string;
    completo?: boolean;
  } | null;
  despesas_por_ano?: Array<{
    ano?: number;
    total?: number;
    qtd_lancamentos?: number;
    por_tipo?: Array<{ tipo: string; valor: number }>;
    fornecedores?: Array<{
      cnpj?: string | null;
      nome?: string | null;
      valor?: number;
      qtd?: number;
    }>;
  }> | null;
  bens_declarados?: {
    qtd?: number;
    valor_total?: number;
    amostra?: Array<{ tipo?: string | null; valor?: number | null }>;
    fonte?: string;
  } | null;
  cnpj?: string | null;
  valor?: number | null;
  contratos_count?: number | null;
  valor_contratos?: number | null;
  rfb_status?: string | null;
  emendas_resumo?: Array<{
    codigo?: string | null;
    valor?: number | null;
    localidade?: string | null;
    ano?: number | null;
    emenda_id?: string | null;
    qtd_documentos?: number | null;
    valor_docs?: number | null;
    beneficiarios?: Array<{
      cnpj?: string | null;
      nome?: string | null;
      orgao?: string | null;
      valor?: number;
      qtd?: number;
    }> | null;
  }> | null;
  campanhas_resumo?: {
    ano?: number | null;
    cargo?: string | null;
    uf?: string | null;
    total_despesas?: number | null;
    qtd_despesas?: number | null;
    fonte?: string;
    fonte_url?: string;
    sq_candidato?: string;
  } | null;
  despesas_campanha?: Array<{
    cnpj?: string | null;
    nome?: string | null;
    valor?: number;
    qtd?: number;
  }> | null;
  legislativo_resumo?: {
    qtd_proposicoes?: number;
    qtd_projetos?: number;
    por_tipo?: Record<string, number>;
    proposicoes_sample?: Array<{
      id?: string;
      label?: string;
      tipo?: string;
      numero?: string | number;
      ano?: string | number;
      data_apresentacao?: string;
      ementa?: string;
    } | string>;
    proposicoes_lista?: Array<{
      id?: string;
      label?: string;
      tipo?: string;
      numero?: string | number;
      ano?: string | number;
      data_apresentacao?: string;
      ementa?: string;
    }>;
    proposicao_ids?: string[];
    votacoes_nominais?: number;
    votos_registrados?: number;
    presente?: number;
    ausente?: number;
    taxa_presenca?: number | null;
    metodo_presenca?: string;
    aviso_presenca?: string;
    por_voto?: Record<string, number>;
    por_ano?: Record<string, { total?: number; presente?: number; ausente?: number }>;
    votos_projetos?: Array<{
      voto?: string;
      data?: string;
      id_proposicao?: string;
      titulo?: string;
      ementa?: string;
      id_votacao?: string;
      descricao_votacao?: string;
    }>;
    votos_por_proposicao?: Array<{
      id_proposicao?: string;
      titulo?: string;
      sigla?: string;
      numero?: string | number;
      ano?: string | number;
      ementa?: string;
      qtd_votacoes?: number;
      ultima_data?: string;
      votos?: Array<{
        voto?: string;
        data?: string;
        id_votacao?: string;
        descricao_votacao?: string;
        orgao?: string;
      }>;
    }>;
    ano_inicio_atividade?: number | null;
    ano_fim_atividade?: number | null;
    anos_atividade?: number | null;
    atualizado_em?: string;
  } | null;
  remuneracao?: {
    cargo?: string;
    serie_subsidio?: Array<{
      ano?: number;
      subsidio_mensal?: number;
      fonte_url?: string;
      nota?: string;
    }>;
    aviso?: string;
    micro_holerite?: boolean;
    frequencia_fonte?: string;
  } | null;
  sancao_resumo?: {
    cadastro?: string | null;
    tipo?: string | null;
    periodo?: string | null;
  } | null;
  autor?: string | null;
  localidade?: string | null;
  funcao?: string | null;
  ano?: number | null;
  tipo_sancao?: string | null;
  periodo?: string | null;
  perfil_fontes?: string[];
  perfil_atualizado_em?: string | null;
  source_ids?: string[];
  sexo?: string | null;
};

export type Caso = {
  id: string;
  nome: string;
  periodo?: string;
  eixos?: string[];
};

export type Registro = {
  id: string;
  pessoa_id: string;
  caso_id: string;
  partido?: string;
  cargo?: string;
  acusacao?: string;
  investigado?: string;
  indiciado?: string;
  reu?: string;
  condenado?: string;
  absolvido?: string;
  situacao_atual?: string;
  status?: string;
  camada?: string;
  fontes?: string[];
};

export type Relacao = {
  id: string;
  origem: string;
  destino: string;
  tipo: string;
  periodo?: string;
  contexto?: string;
  justificativa_documental: string;
  grau_confirmacao: string;
  caso_id?: string | null;
  fontes: string[];
  fonte_ids?: string[];
  url_pendente?: boolean;
  nota?: string;
  confiabilidade?: string;
};
