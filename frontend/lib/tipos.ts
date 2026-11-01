export type Status =
  | "na_fila"
  | "em_andamento"
  | "aguardando_aprovacao"
  | "concluida"
  | "cancelada"
  | "erro"
  | "recusada"
  | "interrompida";

export type ChaveAgente = "supervisor" | "pesquisador" | "redator" | "revisor";
export type TipoTexto = "artigo" | "post" | "relatorio" | "resumo";

export interface Briefing {
  tipo: TipoTexto;
  publico: string;
  tom: string;
  palavras: number;
  idioma: string;
}

export interface Etapa {
  agente: "pesquisador" | "redator" | "revisor";
  objetivo: string;
}

export interface Plano {
  titulo: string;
  abordagem: string;
  perguntas: string[];
  etapas: Etapa[];
}

export interface Fonte {
  id: number;
  titulo: string;
  url: string;
  trecho: string;
  origem: string;
}

export interface Revisao {
  versao: number;
  nota: number;
  aprovado: boolean;
  pontos_fortes: string[];
  problemas: string[];
  sugestoes: string[];
}

export interface ResumoExecucao {
  id: string;
  titulo: string;
  status: Status;
  tipo: TipoTexto;
  criada_em: string;
  atualizada_em: string;
}

export interface Metricas {
  palavras?: number;
  minutos_leitura?: number;
  legibilidade?: number;
  faixa_legibilidade?: string;
  nota?: number | null;
  aprovado?: boolean;
  versoes?: number;
  revisoes?: number;
  fontes_citadas?: number;
  fontes_consultadas?: number;
  duracao_s?: number;
  tokens_entrada?: number;
  tokens_saida?: number;
  passos?: number;
}

export interface Execucao extends ResumoExecucao {
  tarefa: string;
  briefing: Briefing;
  opcoes: { aprovar_plano?: boolean; max_revisoes?: number };
  provedor: string;
  modelo: string;
  plano: Plano | Record<string, never>;
  resultado: string | null;
  fontes: Fonte[];
  metricas: Metricas;
  erro: string | null;
}

export interface Evento {
  seq: number | null;
  tipo: string;
  dados: Record<string, any>;
  criado_em?: string;
}

export interface Agente {
  chave: ChaveAgente;
  nome: string;
  papel: string;
  cor: string;
  prompt_sistema: string;
  temperatura: number;
  ferramentas: string[];
  permitidas: string[];
  max_iteracoes: number;
  modelo: string;
  personalizado: boolean;
}

export interface Ferramenta {
  nome: string;
  descricao: string;
}

export interface Saude {
  versao: string;
  provedor: { nome: string; modelo: string; motivo: string };
  ferramentas: string;
  autenticacao: boolean;
  limites: { contexto: number; notas: number; passos: number; revisoes: number; nota_minima: number };
}
