"""Validação dos parâmetros estruturados de cada perfil de ferramenta.

O mesmo código é usado pelo proxy (antes de exibir e antes de executar) e pelo
executor (que revalida de forma independente antes de montar o ``argv``).
O modelo nunca fornece linha de comando, URL absoluta, host, porta, proxy ou flags.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import Field, StrictInt, ValidationError

from .schemas import Estrito, Limites, PoliticaEscopo


class PolicyError(Exception):
    """Violação de política. ``codigo`` é estável e fica registrado nos eventos."""

    def __init__(self, codigo: str, mensagem: str, detalhes: Optional[dict] = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhes = detalhes or {}

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "mensagem": self.mensagem, "detalhes": self.detalhes}


# Chaves que nunca podem aparecer em parâmetros vindos do modelo.
CHAVES_PROIBIDAS = {
    "host", "hostname", "url", "uri", "porta", "port", "destino", "alvo", "ip", "endereco",
    "proxy", "flags", "flag", "args", "argumentos", "argv", "comando", "command", "cmd",
    "shell", "script", "codigo", "code", "arquivo", "file", "path_local", "redirecionar",
    "seguir_redirecionamentos", "follow_redirects", "resolve", "interface", "env",
}

# Cabeçalhos que nunca são aceitos, mesmo se o manifesto os listar.
CABECALHOS_SEMPRE_BLOQUEADOS = {
    "host", "connection", "content-length", "transfer-encoding", "expect", "upgrade",
    "proxy-authorization", "proxy-connection", "te", "trailer", "forwarded",
    "x-forwarded-for", "x-forwarded-host", "x-real-ip", "via",
}

METODOS_COM_CORPO = {"POST", "PUT", "PATCH"}
METODOS_VALIDOS = {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}

_CAMINHO_RE = re.compile(r"^/[\x21-\x7e]*$")  # ASCII imprimível, sem espaço/controle
_CAB_NOME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,39}$")
_CAB_VALOR_RE = re.compile(r"^[\x20-\x7e]{0,512}$")


class ParametrosHttp(Estrito):
    metodo: str = "GET"
    caminho: str = Field(min_length=1, max_length=2000)
    cabecalhos: dict[str, str] = Field(default_factory=dict)
    corpo: Optional[str] = Field(default=None, max_length=8192)
    max_corpo_bytes: Optional[int] = Field(default=None, ge=0)
    timeout_s: Optional[int] = Field(default=None, ge=1)


class ParametrosScan(Estrito):
    perfil: str = Field(min_length=1, max_length=40)
    portas: list[StrictInt] = Field(min_length=1, max_length=20)
    timeout_s: Optional[int] = Field(default=None, ge=1)


def _checar_chaves(params: dict[str, Any]) -> None:
    if not isinstance(params, dict):
        raise PolicyError("parametros_invalidos", "parametros deve ser um objeto JSON")
    proibidas = sorted(k for k in params if str(k).lower() in CHAVES_PROIBIDAS)
    if proibidas:
        raise PolicyError(
            "parametro_proibido",
            f"parâmetros não permitidos ao modelo: {', '.join(proibidas)} "
            "(host, porta, URL, proxy, flags e comandos são fixados pelo backend)",
            {"chaves": proibidas},
        )


def _converter_erro_pydantic(e: ValidationError) -> PolicyError:
    erros = [{"campo": ".".join(str(p) for p in x["loc"]), "erro": x["msg"]} for x in e.errors()]
    desconhecidos = [x["campo"] for x in erros if "Extra inputs" in x["erro"]]
    if desconhecidos:
        return PolicyError("parametro_desconhecido", f"parâmetros desconhecidos: {', '.join(desconhecidos)}",
                           {"erros": erros})
    return PolicyError("parametros_invalidos", "parâmetros fora do esquema: "
                       + "; ".join(f"{x['campo']}: {x['erro']}" for x in erros), {"erros": erros})


def validar_http(
    params: dict[str, Any],
    politica: PoliticaEscopo,
    limites: Limites,
    *,
    metodos_globais: set[str],
    cabecalhos_globais: set[str],
    permitir_corpo_global: bool,
    max_corpo_requisicao: int = 8192,
) -> dict[str, Any]:
    """Retorna os parâmetros normalizados (com limites efetivos) ou levanta PolicyError."""
    _checar_chaves(params)
    try:
        p = ParametrosHttp(**params)
    except ValidationError as e:
        raise _converter_erro_pydantic(e) from e

    metodo = p.metodo.upper()
    if metodo not in METODOS_VALIDOS:
        raise PolicyError("metodo_invalido", f"método HTTP inválido: {p.metodo}")
    permitidos = {m.upper() for m in politica.metodos} & {m.upper() for m in metodos_globais}
    if metodo not in permitidos:
        raise PolicyError(
            "metodo_nao_permitido",
            f"método {metodo} não permitido (permitidos nesta política: {', '.join(sorted(permitidos)) or 'nenhum'})",
            {"permitidos": sorted(permitidos)},
        )

    caminho = p.caminho
    if not _CAMINHO_RE.match(caminho):
        raise PolicyError("caminho_invalido", "caminho deve ser ASCII imprimível, sem espaços, e começar com '/'")
    if caminho.startswith("//") or caminho.startswith("/\\"):
        raise PolicyError("caminho_invalido", "caminho não pode começar com '//' (URL absoluta/relativa a esquema)")
    if "\\" in caminho:
        raise PolicyError("caminho_invalido", "barra invertida não é permitida no caminho")
    if re.match(r"^/*[A-Za-z][A-Za-z0-9+.-]*://", caminho):
        raise PolicyError("url_absoluta", "URL absoluta não é aceita: use apenas caminho relativo ao alvo da sessão")

    nomes_permitidos = ({c.lower() for c in politica.cabecalhos_permitidos} & {c.lower() for c in cabecalhos_globais}) \
        - CABECALHOS_SEMPRE_BLOQUEADOS
    if len(p.cabecalhos) > 10:
        raise PolicyError("cabecalhos_demais", "no máximo 10 cabeçalhos por requisição")
    cab_norm: dict[str, str] = {}
    for nome, valor in p.cabecalhos.items():
        if not _CAB_NOME_RE.match(nome):
            raise PolicyError("cabecalho_invalido", f"nome de cabeçalho inválido: {nome!r}")
        if nome.lower() in CABECALHOS_SEMPRE_BLOQUEADOS:
            raise PolicyError("cabecalho_proibido", f"cabeçalho {nome} nunca é permitido (ex.: Host arbitrário)")
        if nome.lower() not in nomes_permitidos:
            raise PolicyError("cabecalho_nao_permitido", f"cabeçalho {nome} fora da lista permitida",
                              {"permitidos": sorted(nomes_permitidos)})
        if not _CAB_VALOR_RE.match(valor):
            raise PolicyError("cabecalho_invalido", f"valor inválido para {nome} (CR/LF/controle não permitidos)")
        cab_norm[nome] = valor

    corpo = p.corpo
    if corpo is not None:
        if metodo not in METODOS_COM_CORPO:
            raise PolicyError("corpo_nao_permitido", f"método {metodo} não aceita corpo")
        if not (politica.permitir_corpo and permitir_corpo_global):
            raise PolicyError("corpo_nao_permitido", "envio de corpo desabilitado pela política (global ou do manifesto)")
        if len(corpo.encode("utf-8")) > max_corpo_requisicao:
            raise PolicyError("corpo_grande", f"corpo excede {max_corpo_requisicao} bytes")
        if "\x00" in corpo:
            raise PolicyError("corpo_invalido", "corpo contém byte nulo")

    max_corpo = min(p.max_corpo_bytes if p.max_corpo_bytes is not None else limites.max_corpo_bytes,
                    limites.max_corpo_bytes)
    timeout = min(p.timeout_s if p.timeout_s is not None else limites.timeout_s, limites.timeout_s)
    return {
        "metodo": metodo,
        "caminho": caminho,
        "cabecalhos": cab_norm,
        "corpo": corpo,
        "max_corpo_bytes": int(max_corpo),
        "timeout_s": int(timeout),
    }


def validar_scan(
    params: dict[str, Any],
    politica: PoliticaEscopo,
    limites: Limites,
    *,
    portas_autorizadas: list[int],
    perfis_adaptador: set[str],
) -> dict[str, Any]:
    _checar_chaves(params)
    try:
        p = ParametrosScan(**params)
    except ValidationError as e:
        raise _converter_erro_pydantic(e) from e

    perfis_ok = set(politica.perfis_varredura) & perfis_adaptador
    if p.perfil not in perfis_ok:
        raise PolicyError("perfil_scan_invalido", f"perfil de varredura {p.perfil!r} não permitido",
                          {"permitidos": sorted(perfis_ok)})
    if any(x < 1 or x > 65535 for x in p.portas):
        raise PolicyError("porta_invalida", "portas devem estar entre 1 e 65535")
    portas = sorted(set(p.portas))
    if len(portas) > politica.max_portas:
        raise PolicyError("portas_demais", f"no máximo {politica.max_portas} portas por chamada")
    fora = [x for x in portas if x not in set(portas_autorizadas)]
    if fora:
        raise PolicyError("porta_nao_autorizada",
                          f"porta(s) {fora} não autorizada(s) para esta sessão (autorizadas: {sorted(portas_autorizadas)})",
                          {"autorizadas": sorted(portas_autorizadas), "fora": fora})
    timeout = min(p.timeout_s if p.timeout_s is not None else limites.timeout_s, limites.timeout_s)
    return {"perfil": p.perfil, "portas": portas, "timeout_s": int(timeout)}
