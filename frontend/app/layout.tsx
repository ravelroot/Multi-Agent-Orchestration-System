import "@fontsource-variable/familjen-grotesk";
import "@fontsource-variable/source-serif-4";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import { Casca } from "@/components/Casca";

export const metadata: Metadata = {
  title: "Apogeu",
  description: "Orquestrador de agentes de IA que pesquisam, escrevem e revisam textos com fontes.",
  icons: { icon: "/icone.svg" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e6ddce" },
    { media: "(prefers-color-scheme: dark)", color: "#1d1613" },
  ],
};

const TEMA = `try{var t=localStorage.getItem("apogeu.tema");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;var p=localStorage.getItem("apogeu.paleta");if(p==="bento"||p==="sonda"||p==="nexo")document.documentElement.dataset.palette=p}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: TEMA }} />
      </head>
      <body>
        <Casca>{children}</Casca>
      </body>
    </html>
  );
}
