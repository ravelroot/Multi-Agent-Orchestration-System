"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ROTULO_STATUS, STATUS_ATIVOS } from "@/lib/eventos";
import type { ResumoExecucao, Saude } from "@/lib/tipos";
import { Icone } from "./Icone";
import { Logo } from "./Logo";

export const EVENTO_HISTORICO = "apogeu:historico";

export function avisarHistorico() {
  window.dispatchEvent(new Event(EVENTO_HISTORICO));
}

const NOME_PROVEDOR: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  ollama: "Ollama",
  demonstracao: "Modo demonstração",
};

function quando(iso: string) {
  const data = new Date(iso);
  const hoje = new Date();
  const mesmoDia = data.toDateString() === hoje.toDateString();
  return mesmoDia
    ? `Hoje, ${data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`
    : data.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

function Historico({ fechar }: { fechar: () => void }) {
  const [itens, setItens] = useState<ResumoExecucao[] | null>(null);
  const parametros = useSearchParams();
  const atual = parametros.get("id");

  const carregar = useCallback(() => {
    api.execucoes().then(setItens).catch(() => setItens([]));
  }, []);

  useEffect(() => {
    carregar();
    window.addEventListener(EVENTO_HISTORICO, carregar);
    return () => window.removeEventListener(EVENTO_HISTORICO, carregar);
  }, [carregar]);

  useEffect(() => {
    if (!itens?.some((i) => STATUS_ATIVOS.includes(i.status))) return;
    const id = setInterval(carregar, 4000);
    return () => clearInterval(id);
  }, [itens, carregar]);

  return (
    <nav className="historico" aria-label="Tarefas anteriores">
      <h2>Tarefas</h2>
      {itens === null && <span className="vazio">Carregando...</span>}
      {itens?.length === 0 && <span className="vazio">As tarefas que você criar aparecem aqui.</span>}
      {itens?.map((i) => (
        <Link key={i.id} href={`/?id=${i.id}`} aria-current={i.id === atual} onClick={fechar} title={`${i.titulo} (${ROTULO_STATUS[i.status]})`}>
          <span className="ponto" data-status={i.status} aria-label={ROTULO_STATUS[i.status]} />
          <span className="titulo">{i.titulo}</span>
          <time dateTime={i.criada_em}>{quando(i.criada_em)}</time>
        </Link>
      ))}
    </nav>
  );
}

function SeletorTema() {
  const [tema, setTema] = useState<"system" | "light" | "dark">("system");
  useEffect(() => {
    try {
      const salvo = localStorage.getItem("apogeu.tema");
      if (salvo === "light" || salvo === "dark") setTema(salvo);
    } catch {}
  }, []);
  const escolher = (valor: "system" | "light" | "dark") => {
    setTema(valor);
    if (valor === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = valor;
    try {
      if (valor === "system") localStorage.removeItem("apogeu.tema");
      else localStorage.setItem("apogeu.tema", valor);
    } catch {}
  };
  return (
    <div className="tema" role="group" aria-label="Tema">
      {(["light", "system", "dark"] as const).map((t) => (
        <button key={t} type="button" aria-pressed={tema === t} onClick={() => escolher(t)}>
          {t === "light" ? "Claro" : t === "dark" ? "Escuro" : "Sistema"}
        </button>
      ))}
    </div>
  );
}

const PALETAS = [
  { id: "apogeu", cores: ["#e6ddce", "#a3b4be", "#f6e4a6", "#5d1c16"] },
  { id: "bento", cores: ["#f5f4f4", "#bab7b6", "#4d4b4b", "#000000"] },
  { id: "sonda", cores: ["#f3f1ec", "#7fa7b8", "#17212b", "#a8235a"] },
  { id: "nexo", cores: ["#e8e8e8", "#d9d1ce", "#ab9d9d", "#000000"] },
];

function Cores({ cores }: { cores: readonly string[] }) {
  return (
    <span className="cores" aria-hidden="true">
      {cores.map((c) => (
        <i key={c} style={{ background: c }} />
      ))}
    </span>
  );
}

function SeletorPaleta() {
  const [paleta, setPaleta] = useState("apogeu");
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setPaleta(document.documentElement.dataset.palette ?? "apogeu");
  }, []);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: PointerEvent) => {
      if (!caixa.current?.contains(e.target as Node)) setAberto(false);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAberto(false);
    };
    document.addEventListener("pointerdown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("pointerdown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [aberto]);
  const escolher = (id: string) => {
    setPaleta(id);
    setAberto(false);
    if (id === "apogeu") delete document.documentElement.dataset.palette;
    else document.documentElement.dataset.palette = id;
    try {
      if (id === "apogeu") localStorage.removeItem("apogeu.paleta");
      else localStorage.setItem("apogeu.paleta", id);
    } catch {}
  };
  const atual = PALETAS.find((p) => p.id === paleta) ?? PALETAS[0];
  return (
    <div className="paleta" ref={caixa}>
      <button type="button" className="paleta-botao" aria-haspopup="menu" aria-expanded={aberto} onClick={() => setAberto(!aberto)} title="Paleta de cores">
        <Icone nome="paleta" />
        <span>Paleta de cores</span>
        <Cores cores={atual.cores} />
      </button>
      {aberto && (
        <div className="paleta-menu" role="menu" aria-label="Paleta de cores">
          {PALETAS.map((p, i) => (
            <button key={p.id} type="button" role="menuitemradio" aria-checked={p.id === paleta} aria-label={`Paleta ${i + 1}`} onClick={() => escolher(p.id)}>
              <span>{p.id === paleta ? "✓" : ""}</span>
              <Cores cores={p.cores} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Casca({ children }: { children: React.ReactNode }) {
  const [aberta, setAberta] = useState(false);
  const [saude, setSaude] = useState<Saude | null>(null);
  const caminho = usePathname();
  const fechar = () => setAberta(false);

  useEffect(() => {
    api.saude().then(setSaude).catch(() => setSaude(null));
  }, []);

  return (
    <div className="app">
      <aside className="lateral" data-aberta={aberta}>
        <Link href="/" className="marca" onClick={fechar}>
          <Logo />
          <span>Apogeu</span>
        </Link>
        <Link href="/" className="botao primario" onClick={fechar}>
          <Icone nome="mais" />
          Nova tarefa
        </Link>
        <div className="nav">
          <Link href="/equipe/" aria-current={caminho?.startsWith("/equipe") ? "page" : undefined} onClick={fechar}>
            <Icone nome="equipe" />
            Equipe e prompts
          </Link>
        </div>
        <Suspense fallback={null}>
          <Historico fechar={fechar} />
        </Suspense>
        <div className="rodape-lateral">
          <div className="provedor">
            {saude ? (
              <>
                <strong>{NOME_PROVEDOR[saude.provedor.nome] ?? saude.provedor.nome}</strong>
                {saude.provedor.nome === "demonstracao" ? "Respostas de exemplo, sem chave de API" : saude.provedor.modelo}
              </>
            ) : (
              <>
                <strong>API fora do ar</strong>
                Rode iniciar.cmd ou python -m apogeu
              </>
            )}
          </div>
          <SeletorPaleta />
          <SeletorTema />
        </div>
      </aside>
      <div className="principal">
        <header className="topo-movel">
          <Link href="/" className="marca">
            <Logo />
            <span>Apogeu</span>
          </Link>
          <button type="button" className="botao sutil" onClick={() => setAberta(!aberta)} aria-label={aberta ? "Fechar menu" : "Abrir menu"}>
            <Icone nome={aberta ? "fechar" : "menu"} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}
