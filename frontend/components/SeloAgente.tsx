import { AGENTES } from "@/lib/eventos";
import type { ChaveAgente } from "@/lib/tipos";

export function SeloAgente({ agente, pequeno = false }: { agente: ChaveAgente | null; pequeno?: boolean }) {
  const dados = AGENTES.find((a) => a.chave === agente);
  return (
    <span className={`selo-agente${pequeno ? " pequeno" : ""}`} data-agente={agente ?? "nenhum"} title={dados?.nome ?? "Você"} aria-hidden="true">
      {dados?.sigla ?? "•"}
    </span>
  );
}
