import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const BASE = process.env.APOGEU_URL ?? "http://127.0.0.1:8000";
const PASTA = process.argv[2] ?? "docs/images";
mkdirSync(PASTA, { recursive: true });

const navegador = await chromium.launch();

async function pagina(opcoes = {}) {
  const contexto = await navegador.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, ...opcoes });
  return contexto.newPage();
}

async function tema(p, valor) {
  await p.evaluate((v) => {
    localStorage.setItem("apogeu.tema", v);
    document.documentElement.dataset.theme = v;
  }, valor);
}

async function criarTarefa(p, texto, aprovar = false) {
  await p.goto(BASE + "/");
  await p.fill("#tarefa", texto);
  if (aprovar) await p.check("#aprovar");
  await p.click("button[type=submit]");
  await p.waitForURL(/\?id=/);
}

const p = await pagina();
await p.goto(BASE + "/");
await tema(p, "light");
await p.reload();
await p.fill("#tarefa", "Escreva um artigo sobre como a energia solar residencial evoluiu no Brasil e quanto custa instalar hoje");
await p.screenshot({ path: `${PASTA}/tela-nova-tarefa.png` });

await p.click("button[type=submit]");
await p.waitForURL(/\?id=/);
await p.waitForSelector(".cursor-escrita", { timeout: 30000 });
await p.waitForTimeout(1200);
await p.screenshot({ path: `${PASTA}/tela-equipe-trabalhando.png` });
await p.waitForSelector("text=Texto final pronto", { timeout: 60000 });
await p.waitForTimeout(500);
await p.screenshot({ path: `${PASTA}/tela-texto-final.png` });
await p.click("role=tab[name=/Revisões/]");
await p.screenshot({ path: `${PASTA}/tela-revisoes.png` });
await p.click("role=tab[name=/Fontes/]");
await p.screenshot({ path: `${PASTA}/tela-fontes.png` });
await p.click("role=tab[name=/Texto/]");
const ferramenta = p.locator(".ferramenta").first();
await ferramenta.locator("summary").click();
await ferramenta.scrollIntoViewIfNeeded();
await p.screenshot({ path: `${PASTA}/tela-ferramentas.png` });

await criarTarefa(p, "Crie um post de blog explicando o que são agentes de IA para pequenas empresas", true);
await p.waitForSelector(".aprovacao", { timeout: 30000 });
await p.waitForTimeout(400);
await p.screenshot({ path: `${PASTA}/tela-aprovacao.png` });
await p.click("text=Aprovar plano");
await p.waitForSelector("text=Texto final pronto", { timeout: 60000 });

await p.goto(BASE + "/equipe/");
await p.waitForSelector(".editor-agente");
await p.click(".lista-agentes button:nth-child(2)");
await p.waitForTimeout(300);
await p.screenshot({ path: `${PASTA}/tela-equipe.png` });

await tema(p, "dark");
await p.goto(BASE + "/");
await p.click(".historico a >> nth=1");
await p.waitForSelector("text=Texto final pronto", { timeout: 30000 });
await p.waitForTimeout(400);
await p.screenshot({ path: `${PASTA}/tela-escuro.png` });

const celular = await pagina({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true });
await celular.goto(BASE + "/");
await tema(celular, "light");
await celular.goto(BASE + "/");
await celular.click(".topo-movel button");
await celular.click(".historico a >> nth=1");
await celular.waitForSelector("text=Texto final pronto", { timeout: 30000 });
await celular.click("role=tab[name=Texto] >> nth=0");
await celular.waitForTimeout(300);
await celular.screenshot({ path: `${PASTA}/tela-celular.png` });

await navegador.close();
console.log("capturas prontas");
