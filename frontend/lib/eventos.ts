import type { ChaveAgente, Evento, Fonte, Metricas, Plano, Revisao, Status } from "./tipos";

export const AGENTES: { chave: ChaveAgente; nome: string; sigla: string }[] = [
  { chave: "supervisor", nome: "Supervisor", sigla: "S" },
  { chave: "pesquisador", nome: "Pesquisador", sigla: "P" },
  { chave: "redator", nome: "Redator", sigla: "R" },
  { chave: "revisor", nome: "Revisor", sigla: "V" },
];

export const NOME_AGENTE: Record<string, string> = Object.fromEntries(AGENTES.map((a) => [a.chave, a.nome]));

export const NOME_FERRAMENTA: Record<string, string> = {
  buscar_web: "Buscar na web",
  consultar_wikipedia: "Consultar a Wikipédia",
  ler_pagina: "Ler página",
  calcular: "Calcular",
  data_atual: "Data atual",
  contar_palavras: "Contar palavras",
  metricas_do_rascunho: "Medir o rascunho",
  verificar_citacoes: "Verificar citações",
};

export interface EstadoAgente {
  estado: "parado" | "trabalhando" | "concluido";
  atividade: string;
  tokens: number;
  limite: number;
  chamadas: number;
}

export interface ItemLinha {
  id: string;
  tipo: string;
  agente: ChaveAgente | null;
  titulo: string;
  detalhe?: string;
  argumentos?: Record<string, unknown>;
  resultado?: string;
  duracao?: number;
  erro?: boolean;
  pendente?: boolean;
  alerta?: boolean;
  quando?: string;
}

export interface Visao {
  status: Status | null;
  agentes: Record<ChaveAgente, EstadoAgente>;
  linha: ItemLinha[];
  plano: Plano | null;
  rascunho: string;
  versao: number;
  escrevendo: boolean;
  revisoes: Revisao[];
  fontes: Fonte[];
  notas: string;
  resultado: string | null;
  metricas: Metricas | null;
  erro: string | null;
  ultimoSeq: number;
  compactacoes: number;
  inicio: string | null;
}

const agenteVazio = (): EstadoAgente => ({ estado: "parado", atividade: "Aguardando", tokens: 0, limite: 0, chamadas: 0 });

export function visaoInicial(): Visao {
  return {
    status: null,
    agentes: {
      supervisor: agenteVazio(),
      pesquisador: agenteVazio(),
      redator: agenteVazio(),
      revisor: agenteVazio(),
    },
    linha: [],
    plano: null,
    rascunho: "",
    versao: 0,
    escrevendo: false,
    revisoes: [],
    fontes: [],
    notas: "",
    resultado: null,
    metricas: null,
    erro: null,
    ultimoSeq: 0,
    compactacoes: 0,
    inicio: null,
  };
}

function resumoArgumentos(args: Record<string, unknown>): string {
  const valores = Object.values(args ?? {}).filter((v) => v !== "" && v !== null && v !== undefined);
  if (!valores.length) return "";
  const texto = String(valores[0]);
  return texto.length > 80 ? texto.slice(0, 77) + "..." : texto;
}

function comAgente(v: Visao, chave: string, mudanca: Partial<EstadoAgente>): Visao["agentes"] {
  if (!(chave in v.agentes)) return v.agentes;
  const k = chave as ChaveAgente;
  return { ...v.agentes, [k]: { ...v.agentes[k], ...mudanca } };
}

function item(e: Evento, parcial: Omit<ItemLinha, "id" | "quando">): ItemLinha {
  return { id: `${e.seq ?? Math.random()}`, quando: e.criado_em, ...parcial };
}

export function aplicar(v: Visao, e: Evento): Visao {
  const d = e.dados ?? {};
  const seq = e.seq ?? v.ultimoSeq;
  if (e.seq !== null && e.seq <= v.ultimoSeq && e.tipo !== "rascunho.delta") return v;
  const base = { ...v, ultimoSeq: seq };
  switch (e.tipo) {
    case "execucao.criada":
      return { ...base, status: "na_fila", inicio: e.criado_em ?? null };
    case "execucao.iniciada":
      return { ...base, status: "em_andamento" };
    case "agente.iniciou":
      return {
        ...base,
        status: "em_andamento",
        agentes: comAgente(v, d.agente, { estado: "trabalhando", atividade: d.instrucao || "Trabalhando" }),
        escrevendo: d.agente === "redator" ? true : v.escrevendo,
      };
    case "agente.concluiu":
      return {
        ...base,
        agentes: comAgente(v, d.agente, { estado: "concluido", atividade: d.resumo, chamadas: (v.agentes[d.agente as ChaveAgente]?.chamadas ?? 0) + 1 }),
        linha: d.agente === "pesquisador" ? [...v.linha, item(e, { tipo: e.tipo, agente: d.agente, titulo: `Pesquisa concluída: ${d.resumo}`, duracao: d.duracao_ms })] : v.linha,
      };
    case "contexto.uso":
      return { ...base, agentes: comAgente(v, d.agente, { tokens: d.tokens, limite: d.limite }) };
    case "contexto.compactado":
      return {
        ...base,
        compactacoes: v.compactacoes + 1,
        linha: [...v.linha, item(e, { tipo: e.tipo, agente: d.agente, titulo: "Contexto compactado", detalhe: d.motivo, alerta: true })],
      };
    case "agente.aviso":
      return { ...base, linha: [...v.linha, item(e, { tipo: e.tipo, agente: d.agente, titulo: "Aviso", detalhe: d.mensagem, alerta: true })] };
    case "plano.criado":
      return { ...base, plano: d.plano, linha: [...v.linha, item(e, { tipo: e.tipo, agente: "supervisor", titulo: `Plano: ${d.plano?.titulo ?? ""}`, detalhe: d.plano?.abordagem })] };
    case "plano.aguardando":
      return {
        ...base,
        status: "aguardando_aprovacao",
        plano: d.plano,
        agentes: comAgente(v, "supervisor", { estado: "parado", atividade: "Esperando você aprovar o plano" }),
        linha: [...v.linha, item(e, { tipo: e.tipo, agente: "supervisor", titulo: "Plano aguardando sua aprovação", alerta: true })],
      };
    case "plano.aprovado":
      return {
        ...base,
        status: "em_andamento",
        plano: d.plano,
        linha: [...v.linha, item(e, { tipo: e.tipo, agente: null, titulo: d.editado ? "Você aprovou o plano com alterações" : "Você aprovou o plano", detalhe: d.comentario || undefined })],
      };
    case "plano.recusado":
      return { ...base, status: "recusada", linha: [...v.linha, item(e, { tipo: e.tipo, agente: null, titulo: "Você recusou o plano", detalhe: d.comentario || undefined })] };
    case "supervisor.decisao":
      return {
        ...base,
        linha: [
          ...v.linha,
          item(e, {
            tipo: e.tipo,
            agente: "supervisor",
            titulo: d.proximo === "finalizar" ? "Encerrar e montar a versão final" : `Passar para o ${NOME_AGENTE[d.proximo]?.toLowerCase()}`,
            detalhe: `${d.instrucao}${d.motivo ? `\nMotivo: ${d.motivo}` : ""}${d.ajustado ? `\nRegra aplicada: ${d.regra}` : ""}`,
            alerta: d.ajustado,
          }),
        ],
      };
    case "ferramenta.chamada":
      return {
        ...base,
        linha: [
          ...v.linha,
          {
            ...item(e, {
              tipo: e.tipo,
              agente: d.agente,
              titulo: NOME_FERRAMENTA[d.ferramenta] ?? d.ferramenta,
              detalhe: resumoArgumentos(d.argumentos),
              argumentos: d.argumentos,
              pendente: true,
            }),
            id: d.chamada_id,
          },
        ],
        agentes: comAgente(v, d.agente, { atividade: `${NOME_FERRAMENTA[d.ferramenta] ?? d.ferramenta}: ${resumoArgumentos(d.argumentos)}` }),
      };
    case "ferramenta.resultado":
      return {
        ...base,
        linha: v.linha.map((i) =>
          i.id === d.chamada_id ? { ...i, pendente: false, resultado: d.resultado, duracao: d.duracao_ms, erro: d.erro } : i,
        ),
      };
    case "notas.atualizadas":
      return { ...base, notas: d.notas ?? v.notas };
    case "fontes.atualizadas":
      return { ...base, fontes: d.fontes ?? v.fontes };
    case "rascunho.delta":
      if (d.versao > v.versao || !v.escrevendo) {
        return { ...v, versao: d.versao, rascunho: d.versao > v.versao ? d.texto : v.rascunho + d.texto, escrevendo: true };
      }
      return { ...v, rascunho: v.rascunho + d.texto };
    case "rascunho.atualizado":
      return {
        ...base,
        rascunho: d.texto,
        versao: d.versao,
        escrevendo: false,
        linha: [...v.linha, item(e, { tipo: e.tipo, agente: "redator", titulo: `Versão ${d.versao} pronta`, detalhe: `${d.palavras} palavras` })],
      };
    case "revisao.concluida":
      return {
        ...base,
        revisoes: [...v.revisoes, d as Revisao],
        linha: [
          ...v.linha,
          item(e, {
            tipo: e.tipo,
            agente: "revisor",
            titulo: `Nota ${String(d.nota).replace(".", ",")} na versão ${d.versao}: ${d.aprovado ? "aprovada" : "pediu correções"}`,
            detalhe: (d.problemas ?? []).join("\n") || undefined,
          }),
        ],
      };
    case "execucao.concluida":
      return {
        ...base,
        status: "concluida",
        resultado: d.resultado,
        metricas: d.metricas,
        fontes: d.fontes ?? v.fontes,
        escrevendo: false,
        agentes: Object.fromEntries(Object.entries(v.agentes).map(([k, a]) => [k, { ...a, estado: a.estado === "parado" ? "parado" : "concluido" }])) as Visao["agentes"],
        linha: [...v.linha, item(e, { tipo: e.tipo, agente: null, titulo: "Texto final pronto" })],
      };
    case "execucao.cancelada":
      return { ...base, status: "cancelada", escrevendo: false, linha: [...v.linha, item(e, { tipo: e.tipo, agente: null, titulo: "Tarefa cancelada", alerta: true })] };
    case "execucao.erro":
      return {
        ...base,
        status: "erro",
        erro: d.mensagem,
        escrevendo: false,
        linha: [...v.linha, item(e, { tipo: e.tipo, agente: null, titulo: "A tarefa parou com erro", detalhe: d.mensagem, erro: true })],
      };
    default:
      return base;
  }
}

export const ROTULO_STATUS: Record<Status, string> = {
  na_fila: "Na fila",
  em_andamento: "Em andamento",
  aguardando_aprovacao: "Aguardando aprovação",
  concluida: "Concluída",
  cancelada: "Cancelada",
  erro: "Erro",
  recusada: "Plano recusado",
  interrompida: "Interrompida",
};

export const STATUS_ATIVOS: Status[] = ["na_fila", "em_andamento", "aguardando_aprovacao"];
