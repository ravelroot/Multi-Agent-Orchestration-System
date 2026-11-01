"use client";

import { useEffect, useState } from "react";
import { Icone } from "@/components/Icone";
import { SeloAgente } from "@/components/SeloAgente";
import { api } from "@/lib/api";
import { NOME_FERRAMENTA } from "@/lib/eventos";
import type { Agente, Ferramenta } from "@/lib/tipos";

export default function PaginaEquipe() {
  const [agentes, setAgentes] = useState<Agente[]>([]);
  const [ferramentas, setFerramentas] = useState<Ferramenta[]>([]);
  const [selecionado, setSelecionado] = useState<string>("supervisor");
  const [rascunho, setRascunho] = useState<Agente | null>(null);
  const [aviso, setAviso] = useState<{ texto: string; tipo: "ok" | "falha" } | null>(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    api.agentes().then(setAgentes).catch((e) => setAviso({ texto: e.message, tipo: "falha" }));
    api.ferramentas().then(setFerramentas).catch(() => {});
  }, []);

  useEffect(() => {
    const agente = agentes.find((a) => a.chave === selecionado);
    setRascunho(agente ? { ...agente } : null);
    setAviso(null);
  }, [selecionado, agentes]);

  const descricao = (nome: string) => ferramentas.find((f) => f.nome === nome)?.descricao ?? "";

  async function salvar() {
    if (!rascunho) return;
    setSalvando(true);
    try {
      const salvo = await api.salvarAgente(rascunho.chave, {
        prompt_sistema: rascunho.prompt_sistema,
        temperatura: rascunho.temperatura,
        modelo: rascunho.modelo,
        ferramentas: rascunho.ferramentas,
        max_iteracoes: rascunho.max_iteracoes,
      });
      setAgentes((lista) => lista.map((a) => (a.chave === salvo.chave ? salvo : a)));
      setAviso({ texto: "Agente salvo. As próximas tarefas já usam esta versão.", tipo: "ok" });
    } catch (e) {
      setAviso({ texto: e instanceof Error ? e.message : "Não foi possível salvar.", tipo: "falha" });
    } finally {
      setSalvando(false);
    }
  }

  async function restaurar() {
    if (!rascunho) return;
    const salvo = await api.restaurarAgente(rascunho.chave);
    setAgentes((lista) => lista.map((a) => (a.chave === salvo.chave ? salvo : a)));
    setAviso({ texto: "Prompt e ajustes padrão restaurados.", tipo: "ok" });
  }

  return (
    <div className="pagina-equipe">
      <h1>Equipe e prompts</h1>
      <p>Ajuste como cada agente pensa e trabalha. O prompt de sistema define o papel; a temperatura controla a criatividade; as ferramentas definem o que ele pode chamar.</p>
      <div className="grade-equipe">
        <div className="lista-agentes">
          {agentes.map((a) => (
            <button key={a.chave} type="button" aria-pressed={selecionado === a.chave} onClick={() => setSelecionado(a.chave)}>
              <SeloAgente agente={a.chave} />
              <strong>{a.nome}</strong>
              <small>{a.personalizado ? "Personalizado" : "Padrão"}</small>
            </button>
          ))}
        </div>
        {rascunho && (
          <form
            className="editor-agente"
            onSubmit={(e) => {
              e.preventDefault();
              salvar();
            }}
          >
            <header>
              <h2>{rascunho.nome}</h2>
              <p>{rascunho.papel}</p>
            </header>
            <div className="campo">
              <label htmlFor="prompt">Prompt de sistema</label>
              <textarea id="prompt" value={rascunho.prompt_sistema} onChange={(e) => setRascunho({ ...rascunho, prompt_sistema: e.target.value })} />
            </div>
            <div className="linha-campos">
              <div className="campo">
                <label htmlFor="temperatura">Temperatura: {rascunho.temperatura.toFixed(1).replace(".", ",")}</label>
                <input id="temperatura" type="range" min={0} max={1.5} step={0.1} value={rascunho.temperatura} onChange={(e) => setRascunho({ ...rascunho, temperatura: Number(e.target.value) })} />
              </div>
              <div className="campo">
                <label htmlFor="modelo">Modelo próprio (opcional)</label>
                <input id="modelo" placeholder="Usa o modelo padrão do provedor" value={rascunho.modelo} onChange={(e) => setRascunho({ ...rascunho, modelo: e.target.value })} />
              </div>
              {rascunho.permitidas.length > 0 && (
                <div className="campo">
                  <label htmlFor="iteracoes">Chamadas de ferramenta por etapa</label>
                  <input id="iteracoes" type="number" min={1} max={12} value={rascunho.max_iteracoes} onChange={(e) => setRascunho({ ...rascunho, max_iteracoes: Number(e.target.value) })} />
                </div>
              )}
            </div>
            {rascunho.permitidas.length > 0 ? (
              <fieldset className="campo" style={{ border: 0, padding: 0, margin: 0 }}>
                <legend className="rotulo" style={{ marginBottom: 6 }}>Ferramentas</legend>
                <div className="ferramentas-agente">
                  {rascunho.permitidas.map((f) => (
                    <label key={f} htmlFor={`ferramenta-${f}`}>
                      <input
                        id={`ferramenta-${f}`}
                        type="checkbox"
                        checked={rascunho.ferramentas.includes(f)}
                        onChange={(e) =>
                          setRascunho({
                            ...rascunho,
                            ferramentas: e.target.checked ? [...rascunho.ferramentas, f] : rascunho.ferramentas.filter((x) => x !== f),
                          })
                        }
                      />
                      <span>{NOME_FERRAMENTA[f] ?? f}</span>
                      <small>{descricao(f)}</small>
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : (
              <p className="aviso">
                {rascunho.chave === "redator"
                  ? "O redator não chama ferramentas: ele escreve em streaming a partir das notas e das fontes."
                  : "O supervisor não chama ferramentas: ele decide com saída estruturada e regras de segurança."}
              </p>
            )}
            <footer>
              <span className={`aviso ${aviso?.tipo ?? ""}`} role="status">
                {aviso?.texto}
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className="botao sutil" onClick={restaurar}>
                  <Icone nome="restaurar" />
                  Restaurar padrão
                </button>
                <button type="submit" className="botao primario" disabled={salvando}>
                  {salvando ? "Salvando..." : "Salvar agente"}
                </button>
              </div>
            </footer>
          </form>
        )}
      </div>
    </div>
  );
}
