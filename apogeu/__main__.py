import uvicorn

from .api import criar_app
from .config import obter_configuracao


def main() -> None:
    cfg = obter_configuracao()
    print(f"Apogeu em http://{cfg.host}:{cfg.port}")
    uvicorn.run(criar_app(cfg), host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
