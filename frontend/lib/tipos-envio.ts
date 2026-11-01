import type { Briefing, Plano } from "./tipos";

export type { Agente, Execucao, Ferramenta, ResumoExecucao, Saude } from "./tipos";

export interface NovaTarefa {
  tarefa: string;
  briefing: Briefing;
  aprovar_plano: boolean;
  max_revisoes: number;
}

export interface AprovacaoEnvio {
  aprovado: boolean;
  plano?: Plano;
  comentario?: string;
}
