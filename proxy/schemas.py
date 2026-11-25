"""Entradas e saídas estruturadas da plataforma.

Todos os modelos usam ``extra="forbid"``: qualquer campo desconhecido (por exemplo
``host``, ``url`` ou ``flags`` numa proposta do modelo) é rejeitado, nunca ignorado.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

CABECALHOS_PADRAO = [
    "Accept",
    "Accept-Language",
    "User-Agent",
    "Cache-Control",
    "If-None-Match",
    "If-Modified-Since",
    "Authorization",
    "Cookie",
]


class Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Manifesto de ferramenta (dados/ferramentas/<id>/manifest.json)
# --------------------------------------------------------------------------- #
class Limites(Estrito):
    timeout_s: int = Field(20, ge=1, le=300)
    max_saida_bytes: int = Field(1_048_576, ge=1024, le=20_971_520)
    max_corpo_bytes: int = Field(65_536, ge=0, le=5_242_880)


class PoliticaEscopo(Estrito):
    metodos: list[str] = Field(default_factory=lambda: ["GET", "HEAD"])
    cabecalhos_permitidos: list[str] = Field(default_factory=lambda: list(CABECALHOS_PADRAO))
    perfis_varredura: list[str] = Field(default_factory=lambda: ["conectar_tcp"])
    max_portas: int = Field(5, ge=1, le=20)
    permitir_corpo: bool = False


class Manifesto(Estrito):
    id: str
    versao: str = Field(min_length=1, max_length=40)
    nome: Optional[str] = Field(default=None, max_length=80)
    executavel: str = Field(min_length=1, max_length=200)
    perfil: str = Field(min_length=1, max_length=60)
    descricao_modelo: str = Field(min_length=10, max_length=1500)
    documentacao: Optional[str] = Field(default=None, max_length=200)
    limites: Limites = Field(default_factory=Limites)
    politica_escopo: PoliticaEscopo = Field(default_factory=PoliticaEscopo)
    # Informativos: o esquema efetivo vem sempre do adaptador reconhecido.
    esquema_entrada: Optional[dict[str, Any]] = None
    esquema_saida: Optional[dict[str, Any]] = None

    @field_validator("id")
    @classmethod
    def _id_valido(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("id deve casar com ^[a-z0-9][a-z0-9_-]{1,39}$")
        return v

    @field_validator("executavel", "documentacao")
    @classmethod
    def _caminho_relativo(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v.startswith("/") or v.startswith("\\") or ".." in v.replace("\\", "/").split("/") or "\x00" in v:
            raise ValueError("deve ser um caminho relativo simples, sem '..'")
        return v


# --------------------------------------------------------------------------- #
# Alvo e ação normalizada
# --------------------------------------------------------------------------- #
class EscopoAlvo(Estrito):
    """Escopo fixado para a sessão (resultado de ``normalizar_url_alvo``)."""

    modo: Literal["local", "lan"]
    url_informada: str
    url_base: str
    esquema: Literal["http", "https"]
    host: str
    ips_autorizados: list[str]
    ip_efetivo: str
    porta: int = Field(ge=1, le=65535)
    caminho_base: str = ""
    portas_autorizadas: list[int]


class AlvoEfetivo(Estrito):
    esquema: Literal["http", "https"]
    host: str
    ip: str
    porta: int = Field(ge=1, le=65535)
    caminho_base: str = ""
    portas_autorizadas: list[int] = Field(default_factory=list)


class AcaoNormalizada(Estrito):
    ferramenta_id: str
    perfil: str
    parametros: dict[str, Any]
    alvo: AlvoEfetivo
    resumo_legivel: str
    limites: Limites
    avisos: list[str] = Field(default_factory=list)
    verificacoes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Protocolo com o modelo (resposta JSON)
# --------------------------------------------------------------------------- #
class PropostaModelo(Estrito):
    tipo: Literal["proposta"]
    ferramenta: str = Field(min_length=1, max_length=60)
    parametros: dict[str, Any]
    justificativa: str = Field(min_length=3, max_length=2000)
    hipotese: Optional[str] = Field(default=None, max_length=1000)


class MensagemModelo(Estrito):
    tipo: Literal["mensagem"]
    texto: str = Field(min_length=1, max_length=8000)


class SugestaoPlano(Estrito):
    texto: str = Field(min_length=1, max_length=2000)
    item: Optional[str] = Field(default=None, max_length=200)


class RevisaoPlanoModelo(Estrito):
    tipo: Literal["revisao_plano"]
    sugestoes: list[SugestaoPlano] = Field(min_length=1, max_length=20)


class ConclusaoModelo(Estrito):
    tipo: Literal["concluir"]
    texto: str = Field(min_length=1, max_length=8000)


RespostaModelo = Annotated[
    Union[PropostaModelo, MensagemModelo, RevisaoPlanoModelo, ConclusaoModelo],
    Field(discriminator="tipo"),
]
RESPOSTA_MODELO_ADAPTER: TypeAdapter = TypeAdapter(RespostaModelo)


# --------------------------------------------------------------------------- #
# Contrato proxy -> executor
# --------------------------------------------------------------------------- #
class RequisicaoExecutor(Estrito):
    exec_id: str = Field(pattern=r"^[A-Za-z0-9_-]{4,64}$")
    sessao_id: str = Field(pattern=r"^[A-Za-z0-9_-]{4,64}$")
    ferramenta_id: str
    manifesto_sha256: str
    executavel_sha256: str
    parametros: dict[str, Any]
    alvo: AlvoEfetivo

    @field_validator("manifesto_sha256", "executavel_sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not SHA256_RE.match(v):
            raise ValueError("hash SHA-256 inválido")
        return v


class RespostaExecutor(Estrito):
    exec_id: str
    ok: bool
    argv: list[str] = Field(default_factory=list)
    codigo_saida: Optional[int] = None
    stdout_b64: str = ""
    stderr_b64: str = ""
    truncado: bool = False
    timeout: bool = False
    duracao_ms: int = 0
    erro: Optional[str] = None
    resumo: Optional[dict[str, Any]] = None
    executavel_sha256: Optional[str] = None


class SondagemRequisicao(Estrito):
    esquema: Literal["http", "https"]
    host: str = Field(min_length=1, max_length=253)
    ip: str
    porta: int = Field(ge=1, le=65535)


class DestinoEgress(Estrito):
    ip: str
    porta: int = Field(ge=1, le=65535)
    rotulo: Optional[str] = Field(default=None, max_length=80)


class VerificacaoEgressRequisicao(Estrito):
    destinos: list[DestinoEgress] = Field(min_length=1, max_length=12)
