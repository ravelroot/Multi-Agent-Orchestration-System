from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import RAIZ


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APOGEU_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = Path("data")
    database_url: str = ""
    token: str = ""
    cors_origens: str = "http://localhost:3000,http://127.0.0.1:3000"

    provedor: str = "auto"
    modelo: str = ""
    temperatura: float = 0.3
    timeout_llm: int = 120
    max_tokens_resposta: int = 4096
    ollama_url: str = "http://localhost:11434"
    openai_base_url: str = ""
    openai_api_key: str = Field("", validation_alias=AliasChoices("OPENAI_API_KEY", "APOGEU_OPENAI_API_KEY"))
    anthropic_api_key: str = Field("", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "APOGEU_ANTHROPIC_API_KEY"))
    tavily_api_key: str = Field("", validation_alias=AliasChoices("TAVILY_API_KEY", "APOGEU_TAVILY_API_KEY"))

    busca: str = "duckduckgo"
    ferramentas: str = "reais"
    regiao_busca: str = "br-pt"
    timeout_ferramentas: int = 20

    limite_contexto: int = 12000
    limite_notas: int = 4500
    limite_saida_ferramenta: int = 4000
    max_passos: int = 12
    max_revisoes: int = 2
    max_pesquisas: int = 2
    max_execucoes: int = 3
    nota_minima: float = 8.0
    atraso_demonstracao: float = 0.02

    @property
    def pasta_dados(self) -> Path:
        pasta = self.data_dir if self.data_dir.is_absolute() else RAIZ / self.data_dir
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    @property
    def url_banco(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.pasta_dados / 'apogeu.db').as_posix()}"

    @property
    def origens(self) -> list[str]:
        return [o.strip() for o in self.cors_origens.split(",") if o.strip()]

    @property
    def ferramentas_simuladas(self) -> bool:
        return self.ferramentas.lower() in {"simuladas", "simulada", "offline"}


@lru_cache
def obter_configuracao() -> Configuracao:
    return Configuracao()
