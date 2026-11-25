"""Política de escopo, validação e limites.

Aplicada **duas vezes** para cada ação: antes de exibi-la ao operador e imediatamente
antes de executá-la (após qualquer edição). O modelo nunca escolhe host, porta ou IP.
"""
from __future__ import annotations

import ipaddress
import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from .params import PolicyError, validar_http, validar_scan
from .schemas import (
    AcaoNormalizada,
    AlvoEfetivo,
    EscopoAlvo,
    Manifesto,
    PropostaModelo,
)

# Perfis de ferramenta reconhecidos pela plataforma (cada um tem adaptador no executor).
PERFIL_HTTP = "http_client_curl"
PERFIL_SCAN = "port_scanner_nmap"
PERFIS_RECONHECIDOS = {PERFIL_HTTP, PERFIL_SCAN}
PERFIS_SCAN_ADAPTADOR = {"conectar_tcp", "versao_servico"}

# Descrição dos parâmetros por perfil, mostrada ao modelo (o esquema efetivo é imposto por proxy/params.py).
ESQUEMA_PERFIL: dict[str, dict] = {
    PERFIL_HTTP: {
        "metodo": "GET | HEAD (outros só se a política do manifesto e a global permitirem)",
        "caminho": "caminho relativo ao alvo da sessão, começando com '/', ex.: /rest/products/search?q=apple",
        "cabecalhos": "objeto opcional {nome: valor}; apenas nomes permitidos pela política",
        "max_corpo_bytes": "opcional; limite de bytes de corpo registrados",
        "timeout_s": "opcional; limitado pelo manifesto",
        "observacao": "host, porta, URL absoluta, proxy e flags NÃO existem: são fixados pelo backend",
    },
    PERFIL_SCAN: {
        "perfil": "um de ['conectar_tcp', 'versao_servico'] (limitado pelo manifesto)",
        "portas": "lista de inteiros; somente portas explicitamente autorizadas para a sessão",
        "timeout_s": "opcional; limitado pelo manifesto",
        "observacao": "o host é sempre o IP aprovado do alvo; scripts/NSE e flags livres não existem",
    },
}

HOSTS_RESERVADOS = {"localhost", "agente", "executor", "ollama", "web-ui", "juice-reset", "host.docker.internal.invalid"}
HOST_LOCAL_PERMITIDO = "juice-shop"

Resolver = Callable[[str], list[str]]


def _csv(valor: Optional[str], padrao: list[str]) -> list[str]:
    if valor is None or not valor.strip():
        return padrao
    return [x.strip() for x in valor.split(",") if x.strip()]


@dataclass
class ConfigPolitica:
    metodos_permitidos: set[str] = field(default_factory=lambda: {"GET", "HEAD"})
    cabecalhos_permitidos: set[str] = field(default_factory=lambda: {
        "Accept", "Accept-Language", "User-Agent", "Cache-Control", "If-None-Match",
        "If-Modified-Since", "Authorization", "Cookie"})
    permitir_alvos_publicos: bool = False
    permitir_corpo: bool = False
    max_corpo_requisicao: int = 8192
    max_timeout_s: int = 60
    max_saida_bytes: int = 5_242_880
    max_passos_por_investigacao: int = 25
    max_chamadas_por_minuto: int = 20
    max_bloqueios_consecutivos: int = 3
    max_portas_autorizadas: int = 10

    @classmethod
    def from_env(cls, env: Optional[dict[str, str]] = None) -> "ConfigPolitica":
        e = env if env is not None else os.environ
        return cls(
            metodos_permitidos={m.upper() for m in _csv(e.get("METODOS_PERMITIDOS"), ["GET", "HEAD"])},
            permitir_alvos_publicos=e.get("PERMITIR_ALVOS_PUBLICOS", "false").lower() == "true",
            permitir_corpo=e.get("PERMITIR_CORPO_REQUISICAO", "false").lower() == "true",
            max_corpo_requisicao=int(e.get("MAX_CORPO_REQUISICAO", "8192")),
            max_timeout_s=int(e.get("MAX_TIMEOUT_S", "60")),
            max_saida_bytes=int(e.get("MAX_SAIDA_BYTES", "5242880")),
            max_passos_por_investigacao=int(e.get("MAX_PASSOS_POR_INVESTIGACAO", "25")),
            max_chamadas_por_minuto=int(e.get("MAX_CHAMADAS_POR_MINUTO", "20")),
            max_bloqueios_consecutivos=int(e.get("MAX_BLOQUEIOS_CONSECUTIVOS", "3")),
        )


# --------------------------------------------------------------------------- #
# Alvo
# --------------------------------------------------------------------------- #
def _validar_ip(ip: str, cfg: ConfigPolitica) -> None:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError as e:
        raise PolicyError("ip_invalido", f"endereço IP inválido: {ip}") from e
    if a.is_loopback:
        raise PolicyError("alvo_loopback", f"{ip} é loopback (aponta para o próprio contêiner, não para o alvo). "
                          "Use o IP da LAN do computador que hospeda o Juice Shop.")
    if a.is_unspecified or a.is_multicast or a.is_reserved:
        raise PolicyError("alvo_ip_nao_permitido", f"{ip} não é um destino unicast válido")
    if a.is_link_local:
        raise PolicyError("alvo_link_local", f"{ip} é link-local (inclui endpoints de metadados de nuvem)")
    if a.is_global and not cfg.permitir_alvos_publicos:
        raise PolicyError("alvo_publico", f"{ip} é um endereço público; somente alvos da LAN do laboratório são aceitos "
                          "(PERMITIR_ALVOS_PUBLICOS=false)")


def _host_e_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def normalizar_url_alvo(
    url: str,
    *,
    modo: str,
    resolver: Resolver,
    cfg: ConfigPolitica,
    portas_extra: Optional[list[int]] = None,
) -> EscopoAlvo:
    """Valida a URL informada pelo usuário e fixa os IPs autorizados da sessão.

    Esta é a **única** função que aceita URL absoluta.
    """
    if modo not in ("local", "lan"):
        raise PolicyError("modo_invalido", "modo deve ser 'local' ou 'lan'")
    if not isinstance(url, str) or not url.strip():
        raise PolicyError("url_invalida", "URL vazia")
    url = url.strip()
    if len(url) > 300 or re.search(r"[\s\x00-\x1f\x7f\\]", url):
        raise PolicyError("url_invalida", "URL contém espaços/controle ou é longa demais")
    try:
        partes = urlsplit(url)
        porta_url = partes.port
    except ValueError as e:
        raise PolicyError("url_invalida", f"URL inválida: {e}") from e
    if partes.scheme not in ("http", "https"):
        raise PolicyError("esquema_invalido", "somente http ou https")
    if partes.username or partes.password:
        raise PolicyError("url_invalida", "credenciais embutidas na URL não são permitidas")
    if partes.query or partes.fragment:
        raise PolicyError("url_invalida", "informe apenas esquema, host, porta e caminho base (sem query/fragmento)")
    host = (partes.hostname or "").lower()
    if not host:
        raise PolicyError("url_invalida", "host ausente")
    porta = porta_url or (443 if partes.scheme == "https" else 80)

    if modo == "local":
        if host != HOST_LOCAL_PERMITIDO:
            raise PolicyError("modo_local_host", f"no modo local o alvo é sempre {HOST_LOCAL_PERMITIDO}:3000")
    elif host in HOSTS_RESERVADOS or host == HOST_LOCAL_PERMITIDO:
        raise PolicyError("host_reservado", f"{host} é um serviço da própria plataforma e não pode ser alvo")

    caminho_base = partes.path.rstrip("/")
    if caminho_base and not re.match(r"^/[\x21-\x7e]*$", caminho_base):
        raise PolicyError("url_invalida", "caminho base inválido")

    try:
        ips = [host.strip("[]")] if _host_e_ip_literal(host) else list(dict.fromkeys(resolver(host)))
    except PolicyError:
        raise
    except Exception as e:  # noqa: BLE001
        raise PolicyError("dns_falhou", f"não foi possível resolver {host}: {e}") from e
    if not ips:
        raise PolicyError("dns_falhou", f"{host} não resolveu para nenhum IP")
    if len(ips) > 4:
        raise PolicyError("dns_ambiguo", f"{host} resolve para {len(ips)} IPs; use o IP diretamente")
    for ip in ips:
        _validar_ip(ip, cfg)

    portas = [porta]
    for p in portas_extra or []:
        if not isinstance(p, int) or isinstance(p, bool) or not (1 <= p <= 65535):
            raise PolicyError("porta_invalida", f"porta extra inválida: {p!r}")
        if p not in portas:
            portas.append(p)
    if len(portas) > cfg.max_portas_autorizadas:
        raise PolicyError("portas_demais", f"no máximo {cfg.max_portas_autorizadas} portas autorizadas")

    host_url = f"[{host}]" if ":" in host and not host.startswith("[") else host
    porta_padrao = (partes.scheme == "http" and porta == 80) or (partes.scheme == "https" and porta == 443)
    url_base = f"{partes.scheme}://{host_url}{'' if porta_padrao else f':{porta}'}{caminho_base}/"
    return EscopoAlvo(
        modo=modo, url_informada=url, url_base=url_base, esquema=partes.scheme, host=host,
        ips_autorizados=ips, ip_efetivo=ips[0], porta=porta, caminho_base=caminho_base,
        portas_autorizadas=sorted(portas),
    )


def revalidar_resolucao(escopo: EscopoAlvo, resolver: Resolver) -> None:
    """Impede que mudanças de DNS desviem o tráfego (DNS rebinding)."""
    if _host_e_ip_literal(escopo.host):
        return
    try:
        atuais = set(resolver(escopo.host))
    except Exception as e:  # noqa: BLE001
        raise PolicyError("dns_falhou", f"revalidação de DNS falhou para {escopo.host}: {e}") from e
    if not atuais or not atuais.issubset(set(escopo.ips_autorizados)):
        raise PolicyError(
            "dns_alterado",
            f"a resolução de {escopo.host} mudou ({sorted(atuais)}) e não corresponde aos IPs fixados "
            f"({escopo.ips_autorizados}); ação bloqueada",
            {"atuais": sorted(atuais), "autorizados": escopo.ips_autorizados},
        )


def alvo_efetivo(escopo: EscopoAlvo) -> AlvoEfetivo:
    return AlvoEfetivo(
        esquema=escopo.esquema, host=escopo.host, ip=escopo.ip_efetivo, porta=escopo.porta,
        caminho_base=escopo.caminho_base, portas_autorizadas=list(escopo.portas_autorizadas),
    )


# --------------------------------------------------------------------------- #
# Proposta -> ação normalizada
# --------------------------------------------------------------------------- #
def validar_parametros(
    manifesto: Manifesto,
    parametros: dict[str, Any],
    escopo: EscopoAlvo,
    cfg: ConfigPolitica,
) -> AcaoNormalizada:
    """Valida parâmetros (originais do modelo ou editados pelo operador) e normaliza."""
    limites = manifesto.limites.model_copy(update={
        "timeout_s": min(manifesto.limites.timeout_s, cfg.max_timeout_s),
        "max_saida_bytes": min(manifesto.limites.max_saida_bytes, cfg.max_saida_bytes),
    })
    alvo = alvo_efetivo(escopo)
    verificacoes = ["ferramenta habilitada e íntegra", "esquema dos parâmetros", "alvo fixado pelo backend"]
    avisos: list[str] = []

    if manifesto.perfil == PERFIL_HTTP:
        norm = validar_http(
            parametros, manifesto.politica_escopo, limites,
            metodos_globais=cfg.metodos_permitidos, cabecalhos_globais=cfg.cabecalhos_permitidos,
            permitir_corpo_global=cfg.permitir_corpo, max_corpo_requisicao=cfg.max_corpo_requisicao,
        )
        resumo = f"{norm['metodo']} {escopo.url_base.rstrip('/')}{norm['caminho']}"
        verificacoes += ["método permitido", "caminho relativo", "cabeçalhos na lista permitida"]
        if "Authorization" in norm["cabecalhos"] or "Cookie" in norm["cabecalhos"]:
            avisos.append("A ação envia credenciais (Authorization/Cookie); elas serão ocultadas em exportações.")
    elif manifesto.perfil == PERFIL_SCAN:
        norm = validar_scan(
            parametros, manifesto.politica_escopo, limites,
            portas_autorizadas=escopo.portas_autorizadas, perfis_adaptador=PERFIS_SCAN_ADAPTADOR,
        )
        resumo = f"varredura TCP [{norm['perfil']}] em {escopo.ip_efetivo} portas {','.join(map(str, norm['portas']))}"
        verificacoes += ["perfil de varredura predefinido", "portas autorizadas"]
    else:
        raise PolicyError("perfil_desconhecido", f"perfil {manifesto.perfil!r} sem adaptador revisado")

    limites_efetivos = limites.model_copy(update={"timeout_s": norm["timeout_s"]})
    return AcaoNormalizada(
        ferramenta_id=manifesto.id, perfil=manifesto.perfil, parametros=norm, alvo=alvo,
        resumo_legivel=resumo, limites=limites_efetivos, avisos=avisos, verificacoes=verificacoes,
    )


def validar_proposta(
    proposta: PropostaModelo,
    manifesto: Optional[Manifesto],
    escopo: EscopoAlvo,
    cfg: ConfigPolitica,
    *,
    ferramenta_habilitada: bool,
) -> AcaoNormalizada:
    if manifesto is None or not ferramenta_habilitada:
        raise PolicyError("ferramenta_indisponivel",
                          f"ferramenta {proposta.ferramenta!r} não está habilitada (ou está suspensa/sem documentação)")
    if manifesto.id != proposta.ferramenta:
        raise PolicyError("ferramenta_inconsistente", "id da ferramenta não confere")
    return validar_parametros(manifesto, proposta.parametros, escopo, cfg)


# --------------------------------------------------------------------------- #
# Taxa e concorrência
# --------------------------------------------------------------------------- #
class LimitadorTaxa:
    """Janela deslizante de 60 s por sessão + um único lugar para checar concorrência."""

    def __init__(self, max_por_minuto: int):
        self.max = max_por_minuto
        self._tempos: dict[str, deque[float]] = defaultdict(deque)
        self._ativos: set[str] = set()
        self._lock = threading.Lock()

    def reservar(self, sessao_id: str, agora: Optional[float] = None) -> None:
        t = agora if agora is not None else time.monotonic()
        with self._lock:
            if sessao_id in self._ativos:
                raise PolicyError("concorrencia", "já existe uma execução em andamento nesta sessão")
            q = self._tempos[sessao_id]
            while q and t - q[0] > 60:
                q.popleft()
            if len(q) >= self.max:
                raise PolicyError("taxa_excedida", f"limite de {self.max} chamadas por minuto atingido")
            q.append(t)
            self._ativos.add(sessao_id)

    def liberar(self, sessao_id: str) -> None:
        with self._lock:
            self._ativos.discard(sessao_id)
