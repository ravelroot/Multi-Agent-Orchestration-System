const CAMINHOS: Record<string, string> = {
  mais: "M12 5v14M5 12h14",
  equipe: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9c0-3.3 2.7-6 6-6s6 2.7 6 6M16 4.2a3.5 3.5 0 0 1 0 6.6M18 14.3c2 .9 3 2.9 3 5.7",
  tarefas: "M4 6h16M4 12h16M4 18h10",
  parar: "M7 7h10v10H7z",
  baixar: "M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 20h14",
  copiar: "M9 9h10v11H9zM5 15V4h10",
  lixeira: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  menu: "M4 7h16M4 12h16M4 17h16",
  fechar: "M6 6l12 12M18 6 6 18",
  ok: "M5 12.5 10 17l9-10",
  restaurar: "M4 12a8 8 0 1 0 2.3-5.7M4 4v5h5",
};

export function Icone({ nome }: { nome: keyof typeof CAMINHOS }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={CAMINHOS[nome]} />
    </svg>
  );
}
