"""Configuração do agente (variáveis de ambiente)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from proxy.policy import ConfigPolitica


@dataclass
class Config:
    dados_dir: Path
    ollama_url: str = "http://ollama:11434"
    executor_url: str = "http://executor:8001"
    executor_token: str = ""
    reset_url: Optional[str] = None
    reset_token: str = ""
    politica: ConfigPolitica = field(default_factory=ConfigPolitica)
    turno_sincrono: bool = False
    ollama_timeout_s: float = 600.0
    ollama_temperatura: float = 0.2
    max_historico_chars: int = 24_000
    max_resumo_chars: int = 4_000
    max_doc_chars: int = 6_000
    max_reparos_json: int = 1
    egress_destinos_bloqueados: list[str] = field(default_factory=lambda: ["1.1.1.1:443", "8.8.8.8:53"])

    @property
    def ferramentas_dir(self) -> Path:
        return self.dados_dir / "ferramentas"

    @property
    def documentacoes_dir(self) -> Path:
        return self.dados_dir / "documentacoes"

    @property
    def shared_dir(self) -> Path:
        return self.dados_dir / "__shared__"

    @property
    def importar_dir(self) -> Path:
        return self.dados_dir / "modelos" / "importar"

    @property
    def sessoes_dir(self) -> Path:
        return self.dados_dir / "sessoes"

    @property
    def banco_dir(self) -> Path:
        return self.dados_dir / "banco"

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ
        extra = [x.strip() for x in e.get("EGRESS_TESTE_BLOQUEADOS", "").split(",") if x.strip()]
        return cls(
            dados_dir=Path(e.get("DADOS_DIR", "/dados")),
            ollama_url=e.get("OLLAMA_URL", "http://ollama:11434"),
            executor_url=e.get("EXECUTOR_URL", "http://executor:8001"),
            executor_token=e.get("EXECUTOR_TOKEN", ""),
            reset_url=e.get("RESET_URL") or None,
            reset_token=e.get("RESET_TOKEN", ""),
            politica=ConfigPolitica.from_env(),
            turno_sincrono=e.get("TURNO_SINCRONO", "false").lower() == "true",
            ollama_timeout_s=float(e.get("OLLAMA_TIMEOUT_S", "600")),
            ollama_temperatura=float(e.get("OLLAMA_TEMPERATURA", "0.2")),
            max_historico_chars=int(e.get("MAX_HISTORICO_CHARS", "24000")),
            egress_destinos_bloqueados=["1.1.1.1:443", "8.8.8.8:53", *extra],
        )
