import type { Agente, AprovacaoEnvio, Execucao, Ferramenta, NovaTarefa, ResumoExecucao, Saude } from "./tipos-envio";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export function lerToken(): string {
  try {
    return localStorage.getItem("apogeu.token") ?? "";
  } catch {
    return "";
  }
}

export function salvarToken(valor: string) {
  try {
    if (valor) localStorage.setItem("apogeu.token", valor);
    else localStorage.removeItem("apogeu.token");
  } catch {}
}

export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

async function pedir<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const token = lerToken();
  const resposta = await fetch(BASE + caminho, {
    ...opcoes,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opcoes.headers ?? {}),
    },
  });
  if (!resposta.ok) {
    let mensagem = `A API respondeu com o código ${resposta.status}.`;
    try {
      const corpo = await resposta.json();
      if (typeof corpo.detail === "string") mensagem = corpo.detail;
      else if (Array.isArray(corpo.detail)) mensagem = corpo.detail.map((d: { msg: string }) => d.msg).join(" ");
    } catch {}
    throw new ErroApi(resposta.status, mensagem);
  }
  if (resposta.status === 204) return undefined as T;
  return resposta.json() as Promise<T>;
}

export const api = {
  saude: () => pedir<Saude>("/api/saude"),
  agentes: () => pedir<Agente[]>("/api/agentes"),
  salvarAgente: (chave: string, dados: Partial<Agente>) =>
    pedir<Agente>(`/api/agentes/${chave}`, { method: "PUT", body: JSON.stringify(dados) }),
  restaurarAgente: (chave: string) => pedir<Agente>(`/api/agentes/${chave}/restaurar`, { method: "POST" }),
  ferramentas: () => pedir<Ferramenta[]>("/api/ferramentas"),
  execucoes: () => pedir<ResumoExecucao[]>("/api/execucoes"),
  criar: (dados: NovaTarefa) => pedir<Execucao>("/api/execucoes", { method: "POST", body: JSON.stringify(dados) }),
  obter: (id: string) => pedir<Execucao>(`/api/execucoes/${id}`),
  excluir: (id: string) => pedir<void>(`/api/execucoes/${id}`, { method: "DELETE" }),
  cancelar: (id: string) => pedir<Execucao>(`/api/execucoes/${id}/cancelar`, { method: "POST" }),
  responderPlano: (id: string, dados: AprovacaoEnvio) =>
    pedir<Execucao>(`/api/execucoes/${id}/aprovacao`, { method: "POST", body: JSON.stringify(dados) }),
  urlEventos: (id: string, desde: number) => {
    const token = lerToken();
    const consulta = new URLSearchParams({ desde: String(desde) });
    if (token) consulta.set("token", token);
    return `${BASE}/api/execucoes/${id}/eventos?${consulta}`;
  },
  baixar: async (id: string, formato: "markdown" | "json") => {
    const token = lerToken();
    const resposta = await fetch(`${BASE}/api/execucoes/${id}/exportar?formato=${formato}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resposta.ok) throw new ErroApi(resposta.status, "Não foi possível exportar esta tarefa.");
    const blob = await resposta.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `apogeu-${id.slice(0, 8)}.${formato === "json" ? "json" : "md"}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  },
};
