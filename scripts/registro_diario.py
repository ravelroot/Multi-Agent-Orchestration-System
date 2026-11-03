import asyncio
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
PASTA = RAIZ / "docs" / "registro"
EXTENSOES = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript (React)", ".css": "CSS", ".yml": "YAML", ".sh": "Shell", ".cmd": "Batch", ".go": "Go"}
IGNORAR = {"node_modules", ".next", "out", ".venv", "data", ".git", "__pycache__"}


def agora() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def gravar(nome: str, titulo: str, corpo: str) -> Path:
    PASTA.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA / nome
    arquivo.write_text(f"# {titulo}\n\nAtualizado em {agora()} (Brasília).\n\n{corpo.strip()}\n", encoding="utf-8")
    return arquivo


def testes() -> Path:
    inicio = time.monotonic()
    processo = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider"], cwd=RAIZ, capture_output=True, text=True)
    duracao = time.monotonic() - inicio
    ultima = [l for l in processo.stdout.strip().splitlines() if l.strip()][-1:] or ["sem saída"]
    situacao = "todos passaram" if processo.returncode == 0 else "há falhas"
    corpo = f"| Item | Valor |\n|---|---|\n| Resultado | {ultima[0]} |\n| Situação | {situacao} |\n| Duração | {duracao:.1f} s |\n| Python | {sys.version.split()[0]} |"
    return gravar("testes.md", "Testes automatizados", corpo)


def grafo() -> Path:
    from apogeu.grafo import diagrama_mermaid

    corpo = "Grafo LangGraph compilado a partir de `apogeu/grafo.py`.\n\n```mermaid\n" + diagrama_mermaid().strip() + "\n```"
    return gravar("grafo.md", "Grafo da equipe", corpo)


def equipe() -> Path:
    from apogeu.agentes import PADROES
    from apogeu.ferramentas import catalogo

    linhas = ["| Agente | Temperatura | Ferramentas | Tamanho do prompt |", "|---|---|---|---|"]
    for padrao in PADROES.values():
        ferramentas = ", ".join(f"`{f}`" for f in padrao["ferramentas"]) or "nenhuma"
        linhas.append(f"| {padrao['nome']} | {padrao['temperatura']} | {ferramentas} | {len(padrao['prompt_sistema'].split())} palavras |")
    linhas += ["", "| Ferramenta | Descrição |", "|---|---|"]
    linhas += [f"| `{f['nome']}` | {f['descricao']} |" for f in catalogo()]
    return gravar("equipe.md", "Agentes e ferramentas", "\n".join(linhas))


def codigo() -> Path:
    arquivos: Counter = Counter()
    linhas: Counter = Counter()
    for caminho in RAIZ.rglob("*"):
        if caminho.is_file() and caminho.suffix in EXTENSOES and not (set(caminho.relative_to(RAIZ).parts) & IGNORAR):
            linguagem = EXTENSOES[caminho.suffix]
            arquivos[linguagem] += 1
            linhas[linguagem] += sum(1 for l in caminho.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip())
    tabela = ["| Linguagem | Arquivos | Linhas |", "|---|---|---|"]
    tabela += [f"| {l} | {arquivos[l]} | {linhas[l]} |" for l, _ in linhas.most_common()]
    tabela.append(f"| Total | {sum(arquivos.values())} | {sum(linhas.values())} |")
    return gravar("codigo.md", "Tamanho do código", "\n".join(tabela))


def demonstracao() -> Path:
    from apogeu.agentes import carregar_agentes, garantir_padroes
    from apogeu.config import Configuracao
    from apogeu.db import Repositorio
    from apogeu.grafo import ContextoExecucao, construir_grafo
    from apogeu.llm import resolver_provedor

    with tempfile.TemporaryDirectory() as pasta:
        cfg = Configuracao(data_dir=Path(pasta), provedor="demonstracao", ferramentas="simuladas", atraso_demonstracao=0)
        repo = Repositorio(cfg.url_banco)
        garantir_padroes(repo)
        eventos: Counter = Counter()

        async def emitir(tipo, dados, persistir=True):
            eventos[tipo] += 1

        ctx = ContextoExecucao(cfg=cfg, provedor=resolver_provedor(cfg), agentes=carregar_agentes(repo), emitir=emitir)
        entrada = {"tarefa": "Escreva um artigo sobre o uso de agentes de IA em equipes editoriais", "briefing": {"palavras": 500}, "max_revisoes": 2}
        estado = asyncio.run(construir_grafo().ainvoke(entrada, {"configurable": {"contexto": ctx}, "recursion_limit": 40}))
        repo.engine.dispose()
    m = estado["metricas"]
    corpo = (
        "Execução completa no modo demonstração, com ferramentas simuladas.\n\n"
        "| Métrica | Valor |\n|---|---|\n"
        f"| Nota final | {m['nota']} |\n| Aprovado | {'sim' if m['aprovado'] else 'não'} |\n"
        f"| Versões do rascunho | {m['versoes']} |\n| Palavras | {m['palavras']} |\n"
        f"| Fontes citadas | {m['fontes_citadas']} de {m['fontes_consultadas']} |\n"
        f"| Chamadas de ferramenta | {eventos['ferramenta.chamada']} |\n"
        f"| Tokens estimados | {m['tokens_entrada']} de entrada e {m['tokens_saida']} de saída |\n"
        f"| Passos do supervisor | {m['passos']} |"
    )
    return gravar("demonstracao.md", "Execução de demonstração", corpo)


TURNOS = {"testes": testes, "grafo": grafo, "equipe": equipe, "codigo": codigo, "demonstracao": demonstracao}

if __name__ == "__main__":
    turno = sys.argv[1] if len(sys.argv) > 1 else ""
    if turno not in TURNOS:
        print(f"Use: python scripts/registro_diario.py [{'|'.join(TURNOS)}]")
        sys.exit(2)
    os.environ.setdefault("APOGEU_FERRAMENTAS", "simuladas")
    print(TURNOS[turno]().relative_to(RAIZ))
