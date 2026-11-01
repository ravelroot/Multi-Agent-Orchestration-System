"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Compositor } from "@/components/Compositor";
import { PainelExecucao } from "@/components/PainelExecucao";

function Inicio() {
  const id = useSearchParams().get("id");
  return id ? <PainelExecucao id={id} /> : <Compositor />;
}

export default function Pagina() {
  return (
    <Suspense fallback={<div className="carregando-tela">Carregando...</div>}>
      <Inicio />
    </Suspense>
  );
}
