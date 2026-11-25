"""Perfis (adaptadores) de ferramentas aceitos pelo executor.

Cada adaptador conhece a convenção de argumentos de uma família de ferramentas e monta
o ``argv`` **somente** a partir de parâmetros estruturados já validados. Não existe
caminho para o modelo fornecer flags, script, host ou porta.

Perfis incluídos (a plataforma não inclui os executáveis, só o adaptador):

* ``http_client_curl``  – qualquer executável compatível com as opções do curl usadas abaixo.
* ``port_scanner_nmap`` – qualquer executável compatível com as opções do nmap usadas abaixo.

Para aceitar outra ferramenta é preciso escrever e revisar um novo adaptador neste arquivo.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from proxy.params import PolicyError, validar_http, validar_scan
from proxy.policy import ESQUEMA_PERFIL, PERFIL_HTTP, PERFIL_SCAN, PERFIS_SCAN_ADAPTADOR, ConfigPolitica
from proxy.schemas import AlvoEfetivo, Limites, Manifesto

META_MARCADOR = "<<PLATAFORMA-META>>"
# curl -w: gravado no final da saída; o adaptador separa e valida.
_CURL_WRITEOUT = (
    '\\n' + META_MARCADOR +
    '{"http_code":%{http_code},"time_total":%{time_total},"remote_ip":"%{remote_ip}",'
    '"remote_port":%{remote_port},"size_download":%{size_download}}\\n'
)


class Adaptador:
    perfil: str = ""

    def esquema(self) -> dict[str, Any]:  # descrição usada no contexto do modelo
        raise NotImplementedError

    def validar(self, params: dict, manifesto: Manifesto, alvo: AlvoEfetivo, limites: Limites, cfg: ConfigPolitica) -> dict:
        raise NotImplementedError

    def montar_argv(self, exe: str, params: dict, alvo: AlvoEfetivo, limites: Limites) -> list[str]:
        raise NotImplementedError

    def verificar_argv(self, argv: list[str], alvo: AlvoEfetivo) -> None:
        """Garantia final: o único destino presente no argv é o IP/porta do alvo."""
        raise NotImplementedError

    def interpretar(self, stdout: bytes, stderr: bytes, codigo: int | None, params: dict, alvo: AlvoEfetivo,
                    limites: Limites) -> dict[str, Any]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
class AdaptadorHttpCurl(Adaptador):
    perfil = PERFIL_HTTP

    def esquema(self) -> dict[str, Any]:
        return ESQUEMA_PERFIL[self.perfil]

    def validar(self, params, manifesto, alvo, limites, cfg):
        return validar_http(
            params, manifesto.politica_escopo, limites,
            metodos_globais=cfg.metodos_permitidos, cabecalhos_globais=cfg.cabecalhos_permitidos,
            permitir_corpo_global=cfg.permitir_corpo, max_corpo_requisicao=cfg.max_corpo_requisicao,
        )

    @staticmethod
    def _host_url(alvo: AlvoEfetivo) -> str:
        return f"[{alvo.host}]" if ":" in alvo.host and not alvo.host.startswith("[") else alvo.host

    def url(self, params: dict, alvo: AlvoEfetivo) -> str:
        padrao = (alvo.esquema == "http" and alvo.porta == 80) or (alvo.esquema == "https" and alvo.porta == 443)
        porta = "" if padrao else f":{alvo.porta}"
        return f"{alvo.esquema}://{self._host_url(alvo)}{porta}{alvo.caminho_base}{params['caminho']}"

    def montar_argv(self, exe, params, alvo, limites):
        timeout = int(params["timeout_s"])
        argv = [
            exe, "-q",                       # -q DEVE ser o primeiro: ignora ~/.curlrc
            "-sS", "-i", "-g",               # silencioso c/ erros; inclui cabeçalhos; -g desliga globbing de {}[]
            "--max-time", str(timeout), "--connect-timeout", str(min(timeout, 10)),
            "--max-redirs", "0",             # nunca seguir redirecionamentos
            "--noproxy", "*", "--proto", "=http,https", "--path-as-is",
            "--max-filesize", str(int(params["max_corpo_bytes"]) or 1),
            "-w", _CURL_WRITEOUT,
        ]
        if alvo.esquema == "https":
            argv += ["-k"]                   # laboratório: certificado autoassinado do Juice Shop
        if not _e_ip(alvo.host):
            ip = f"[{alvo.ip}]" if ":" in alvo.ip else alvo.ip
            argv += ["--resolve", f"{alvo.host}:{alvo.porta}:{ip}"]  # conecta somente ao IP autorizado
        metodo = params["metodo"]
        if metodo == "HEAD":
            argv += ["-I"]
        else:
            argv += ["-X", metodo]
        for nome, valor in params["cabecalhos"].items():
            argv += ["-H", f"{nome}: {valor}"]
        if params.get("corpo") is not None:
            argv += ["--data-binary", params["corpo"]]
        argv.append(self.url(params, alvo))
        return argv

    def verificar_argv(self, argv, alvo):
        urls = [a for a in argv if re.match(r"^https?://", a)]
        if len(urls) != 1:
            raise PolicyError("argv_invalido", "o argv deve conter exatamente uma URL")
        proibidos = {"-L", "--location", "-x", "--proxy", "--connect-to", "-K", "--config", "--next", "-:"}
        if proibidos & set(argv):
            raise PolicyError("argv_invalido", "opção proibida no argv")
        from urllib.parse import urlsplit
        p = urlsplit(urls[0])
        porta_url = p.port or (443 if p.scheme == "https" else 80)
        if p.scheme != alvo.esquema or porta_url != alvo.porta:
            raise PolicyError("argv_invalido", "esquema/porta da URL diferem do alvo fixado")
        if (p.hostname or "").lower() != alvo.host.strip("[]").lower():
            raise PolicyError("argv_invalido", "host da URL difere do host fixado")
        if p.username or p.password:
            raise PolicyError("argv_invalido", "credenciais embutidas na URL")

    def interpretar(self, stdout, stderr, codigo, params, alvo, limites):
        texto = stdout.decode("utf-8", errors="replace")
        corpo_total, _, meta_raw = texto.rpartition(META_MARCADOR)
        meta: dict[str, Any] = {}
        if meta_raw:
            try:
                meta = json.loads(meta_raw.strip())
            except json.JSONDecodeError:
                meta = {}
        else:
            corpo_total = texto
        corpo_total = corpo_total.rstrip("\n") if meta_raw else corpo_total
        cab_txt, sep, corpo = corpo_total.partition("\r\n\r\n")
        if not sep:
            cab_txt, sep, corpo = corpo_total.partition("\n\n")
        linhas = [l for l in cab_txt.replace("\r", "").split("\n") if l.strip()]
        status_linha = linhas[0] if linhas else ""
        m = re.match(r"^HTTP/[\d.]+\s+(\d{3})", status_linha)
        cabecalhos = []
        for l in linhas[1:]:
            k, _, v = l.partition(":")
            cabecalhos.append([k.strip(), v.strip()])
        limite = int(params["max_corpo_bytes"])
        corpo_b = corpo.encode("utf-8", errors="replace")
        resumo: dict[str, Any] = {
            "tipo": "http",
            "requisicao": {
                "metodo": params["metodo"],
                "url": self.url(params, alvo),
                "cabecalhos_enviados": sorted(params["cabecalhos"].keys()),
            },
            "status": int(m.group(1)) if m else meta.get("http_code"),
            "linha_status": status_linha,
            "cabecalhos": cabecalhos,
            "corpo_amostra": corpo_b[:limite].decode("utf-8", errors="replace"),
            "corpo_truncado": len(corpo_b) > limite,
            "tempo_s": meta.get("time_total"),
            "ip_remoto": meta.get("remote_ip"),
            "bytes_corpo": meta.get("size_download"),
        }
        if meta.get("remote_ip") and meta["remote_ip"] != alvo.ip:
            resumo["alerta"] = f"IP remoto {meta['remote_ip']} difere do IP autorizado {alvo.ip}"
        if codigo not in (0, None) and stderr:
            resumo["erro"] = stderr.decode("utf-8", errors="replace")[:500]
        return resumo


# --------------------------------------------------------------------------- #
class AdaptadorScanNmap(Adaptador):
    perfil = PERFIL_SCAN
    _FLAGS = {
        "conectar_tcp": ["-sT"],
        "versao_servico": ["-sT", "-sV", "--version-light"],
    }

    def esquema(self) -> dict[str, Any]:
        return ESQUEMA_PERFIL[self.perfil]

    def validar(self, params, manifesto, alvo, limites, cfg):
        return validar_scan(params, manifesto.politica_escopo, limites,
                            portas_autorizadas=alvo.portas_autorizadas, perfis_adaptador=PERFIS_SCAN_ADAPTADOR)

    def montar_argv(self, exe, params, alvo, limites):
        argv = [exe, "-Pn", "-n", "-T3", "--max-retries", "1", "--host-timeout", f"{int(params['timeout_s'])}s",
                *self._FLAGS[params["perfil"]], "-oN", "-", "-p", ",".join(str(p) for p in params["portas"])]
        if ":" in alvo.ip:
            argv.append("-6")
        argv.append(alvo.ip)
        return argv

    def verificar_argv(self, argv, alvo):
        if argv[-1] != alvo.ip:
            raise PolicyError("argv_invalido", "o último argumento deve ser o IP autorizado")
        if any(a.startswith("--script") or a in ("-iL", "-A", "-sU", "-sS", "--datadir", "--proxies") for a in argv):
            raise PolicyError("argv_invalido", "opção proibida no argv")
        ips = [a for a in argv if re.match(r"^[\d.]+$", a) and a.count(".") == 3]
        if any(i != alvo.ip for i in ips):
            raise PolicyError("argv_invalido", "endereço alternativo no argv")

    def interpretar(self, stdout, stderr, codigo, params, alvo, limites):
        texto = stdout.decode("utf-8", errors="replace")
        portas = []
        for l in texto.splitlines():
            m = re.match(r"^(\d+)/(tcp|udp)\s+(\S+)\s+(\S+)\s*(.*)$", l.strip())
            if m:
                portas.append({"porta": int(m.group(1)), "proto": m.group(2), "estado": m.group(3),
                               "servico": m.group(4), "versao": m.group(5).strip() or None})
        resumo = {"tipo": "scan", "perfil": params["perfil"], "alvo_ip": alvo.ip,
                  "portas_solicitadas": params["portas"], "portas": portas, "saida_amostra": texto[:4000]}
        if codigo not in (0, None) and stderr:
            resumo["erro"] = stderr.decode("utf-8", errors="replace")[:500]
        return resumo


def _e_ip(host: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


ADAPTADORES: dict[str, Adaptador] = {a.perfil: a for a in (AdaptadorHttpCurl(), AdaptadorScanNmap())}

# Fábrica pública usada pelo agente para listar esquemas no contexto do modelo.
def esquema_do_perfil(perfil: str) -> dict[str, Any]:
    return ADAPTADORES[perfil].esquema()
