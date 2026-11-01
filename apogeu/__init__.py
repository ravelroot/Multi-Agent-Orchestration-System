from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _ler_versao() -> str:
    arquivo = RAIZ / "VERSION"
    if arquivo.exists():
        return arquivo.read_text(encoding="utf-8").strip()
    return "0.0.0"


__version__ = _ler_versao()
