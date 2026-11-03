import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESKTOP = RAIZ / "desktop"
EXE = RAIZ / "Apogeu.exe"
LOGO = RAIZ / "docs" / "images" / "logo.svg"
TOOLCHAIN = "go1.24.7"
GOVERSIONINFO = "github.com/josephspurrier/goversioninfo/cmd/goversioninfo@v1.5.0"
TAMANHOS = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
AMOSTRAS = 4
MARGEM = 0.05
TRACO_MINIMO = 1.3
RAIO_MINIMO = 1.25


def atributo(elemento: str, nome: str, padrao: float | None = None) -> float:
    achado = re.search(rf'(?<![\w-]){nome}="([-\d.]+)"', elemento)
    if achado:
        return float(achado.group(1))
    if padrao is None:
        raise SystemExit(f"docs/images/logo.svg mudou: falta o atributo {nome} em {elemento}")
    return padrao


def formas() -> list[dict]:
    svg = re.sub(r"<metadata>.*?</metadata>", "", LOGO.read_text(encoding="utf-8"), flags=re.S)
    lista = []
    for elemento in re.findall(r"<ellipse\b[^>]*>", svg):
        cx, cy = atributo(elemento, "cx"), atributo(elemento, "cy")
        giro = re.search(r"rotate\(\s*([-\d.]+)(?:[\s,]+([-\d.]+)[\s,]+([-\d.]+))?\s*\)", elemento)
        angulo = math.radians(float(giro.group(1))) if giro else 0.0
        if giro and giro.group(2) is not None:
            ox, oy = float(giro.group(2)), float(giro.group(3))
            cx, cy = (
                ox + (cx - ox) * math.cos(angulo) - (cy - oy) * math.sin(angulo),
                oy + (cx - ox) * math.sin(angulo) + (cy - oy) * math.cos(angulo),
            )
        lista.append({"tipo": "anel", "cx": cx, "cy": cy, "rx": atributo(elemento, "rx"), "ry": atributo(elemento, "ry"), "angulo": angulo, "traco": atributo(elemento, "stroke-width", 1.0)})
    for elemento in re.findall(r"<circle\b[^>]*>", svg):
        lista.append({"tipo": "disco", "cx": atributo(elemento, "cx"), "cy": atributo(elemento, "cy"), "r": atributo(elemento, "r")})
    if not lista:
        raise SystemExit("docs/images/logo.svg mudou: nenhuma elipse ou círculo encontrado.")
    return lista


def limites(forma: dict) -> tuple[float, float, float, float]:
    if forma["tipo"] == "disco":
        r = forma["r"]
        return forma["cx"] - r, forma["cy"] - r, forma["cx"] + r, forma["cy"] + r
    c, s = math.cos(forma["angulo"]), math.sin(forma["angulo"])
    meia_largura = math.hypot(forma["rx"] * c, forma["ry"] * s) + forma["traco"] / 2
    meia_altura = math.hypot(forma["rx"] * s, forma["ry"] * c) + forma["traco"] / 2
    return forma["cx"] - meia_largura, forma["cy"] - meia_altura, forma["cx"] + meia_largura, forma["cy"] + meia_altura


def cobre(forma: dict, x: float, y: float) -> bool:
    dx, dy = x - forma["cx"], y - forma["cy"]
    if forma["tipo"] == "disco":
        return dx * dx + dy * dy <= forma["r"] * forma["r"]
    c, s = math.cos(forma["angulo"]), math.sin(forma["angulo"])
    qx, qy = dx * c + dy * s, -dx * s + dy * c
    rx2, ry2 = forma["rx"] ** 2, forma["ry"] ** 2
    valor = qx * qx / rx2 + qy * qy / ry2 - 1
    gradiente = 2 * math.hypot(qx / rx2, qy / ry2)
    return gradiente > 0 and abs(valor / gradiente) <= forma["traco"] / 2


def desenhar(lista: list[dict], lado: int) -> bytearray:
    caixas = [limites(f) for f in lista]
    x0, y0 = min(c[0] for c in caixas), min(c[1] for c in caixas)
    x1, y1 = max(c[2] for c in caixas), max(c[3] for c in caixas)
    escala = lado * (1 - 2 * MARGEM) / max(x1 - x0, y1 - y0)
    deslocamento_x = (lado - (x1 - x0) * escala) / 2 - x0 * escala
    deslocamento_y = (lado - (y1 - y0) * escala) / 2 - y0 * escala
    ajustadas = []
    for forma in lista:
        forma = dict(forma)
        if forma["tipo"] == "anel":
            forma["traco"] = max(forma["traco"] * escala, TRACO_MINIMO) / escala
        else:
            forma["r"] = max(forma["r"] * escala, RAIO_MINIMO) / escala
        bx0, by0, bx1, by1 = limites(forma)
        forma["px"] = (math.floor(bx0 * escala + deslocamento_x), math.floor(by0 * escala + deslocamento_y), math.ceil(bx1 * escala + deslocamento_x), math.ceil(by1 * escala + deslocamento_y))
        ajustadas.append(forma)
    passos = [(i + 0.5) / AMOSTRAS for i in range(AMOSTRAS)]
    total = AMOSTRAS * AMOSTRAS
    rgba = bytearray(b"\xff" * (lado * lado * 4))
    for py in range(lado):
        for px in range(lado):
            perto = [f for f in ajustadas if f["px"][0] <= px <= f["px"][2] and f["px"][1] <= py <= f["px"][3]]
            if not perto:
                continue
            acertos = 0
            for sy in passos:
                y = (py + sy - deslocamento_y) / escala
                for sx in passos:
                    x = (px + sx - deslocamento_x) / escala
                    if any(cobre(f, x, y) for f in perto):
                        acertos += 1
            if acertos:
                tom = round(255 * (1 - acertos / total))
                i = (py * lado + px) * 4
                rgba[i] = rgba[i + 1] = rgba[i + 2] = tom
    return rgba


def bmp(rgba: bytearray, lado: int) -> bytes:
    cabecalho = struct.pack("<IiiHHIIiiII", 40, lado, lado * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    cores = bytearray(lado * lado * 4)
    for y in range(lado):
        for x in range(lado):
            de = (y * lado + x) * 4
            para = ((lado - 1 - y) * lado + x) * 4
            cores[para : para + 4] = bytes((rgba[de + 2], rgba[de + 1], rgba[de], rgba[de + 3]))
    mascara = bytes(((lado + 31) // 32) * 4 * lado)
    return cabecalho + bytes(cores) + mascara


def png(rgba: bytearray, lado: int) -> bytes:
    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    linhas = b"".join(b"\x00" + bytes(rgba[y * lado * 4 : (y + 1) * lado * 4]) for y in range(lado))
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 6, 0, 0, 0)) + bloco(b"IDAT", zlib.compress(linhas, 9)) + bloco(b"IEND", b"")


def icone() -> bytes:
    lista = formas()
    imagens = []
    for lado in TAMANHOS:
        rgba = desenhar(lista, lado)
        imagens.append(png(rgba, lado) if lado == 256 else bmp(rgba, lado))
    deslocamento = 6 + 16 * len(TAMANHOS)
    entradas = b""
    for lado, imagem in zip(TAMANHOS, imagens):
        medida = 0 if lado == 256 else lado
        entradas += struct.pack("<BBBBHHII", medida, medida, 0, 0, 1, 32, len(imagem), deslocamento)
        deslocamento += len(imagem)
    return struct.pack("<HHH", 0, 1, len(TAMANHOS)) + entradas + b"".join(imagens)


def informacoes(versao: str) -> dict:
    partes = [int(p) for p in (versao.split(".") + ["0", "0", "0"])[:3]]
    numero = {"Major": partes[0], "Minor": partes[1], "Patch": partes[2], "Build": 0}
    return {
        "FixedFileInfo": {"FileVersion": numero, "ProductVersion": numero, "FileFlagsMask": "3f", "FileFlags": "00", "FileOS": "040004", "FileType": "01", "FileSubType": "00"},
        "StringFileInfo": {
            "Comments": "Abre o Apogeu numa janela própria do Windows: prepara o ambiente na primeira vez, sobe o servidor local e encerra tudo ao fechar.",
            "CompanyName": "Erik Pimenta",
            "FileDescription": "Apogeu, orquestrador de agentes de IA",
            "FileVersion": versao,
            "InternalName": "Apogeu",
            "LegalCopyright": "Copyright (©) 2026 Erik Pimenta. Licença MIT.",
            "OriginalFilename": "Apogeu.exe",
            "ProductName": "Apogeu",
            "ProductVersion": versao,
        },
        "VarFileInfo": {"Translation": {"LangID": "0416", "CharsetID": "04B0"}},
        "IconPath": "apogeu.ico",
        "ManifestPath": "apogeu.manifest",
    }


def go(argumentos: list[str], extra: dict | None = None) -> None:
    ambiente = {**os.environ, "GOTOOLCHAIN": TOOLCHAIN, "GOFLAGS": "-mod=readonly", **(extra or {})}
    subprocess.run(["go", *argumentos], cwd=DESKTOP, env=ambiente, check=True)


def main() -> None:
    if not shutil.which("go"):
        sys.exit("Para gerar o Apogeu.exe é preciso o Go 1.24 ou mais recente (https://go.dev/dl/).")
    versao = (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    (DESKTOP / "apogeu.ico").write_bytes(icone())
    (DESKTOP / "versioninfo.json").write_text(json.dumps(informacoes(versao), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    recursos = ["-64", "-o", "resource_windows_amd64.syso", "versioninfo.json"]
    ferramenta = os.environ.get("APOGEU_GOVERSIONINFO")
    if ferramenta:
        subprocess.run([ferramenta, *recursos], cwd=DESKTOP, check=True)
    else:
        go(["run", GOVERSIONINFO, *recursos])
    go(
        ["build", "-trimpath", "-buildvcs=false", "-ldflags", f"-s -w -buildid= -H=windowsgui -X main.versao={versao}", "-o", str(EXE), "."],
        {"GOOS": "windows", "GOARCH": "amd64", "GOAMD64": "v1", "CGO_ENABLED": "0"},
    )
    print(f"Apogeu.exe {versao} pronto ({EXE.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as erro:
        sys.exit(erro.returncode)
