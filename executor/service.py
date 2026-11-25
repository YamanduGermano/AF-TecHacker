"""API interna do executor.

Executa **somente** ferramentas habilitadas, por chamada autenticada do proxy, sem shell,
com limites de tempo/saída/recursos, usuário sem privilégios e rede restrita (ver compose.yaml
e scripts/aplicar-egress.sh). O executor revalida tudo de forma independente: manifesto,
hash do executável, parâmetros e ``argv``.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import os
import re
import resource
import shutil
import signal
import socket
import ssl
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ValidationError

from proxy.params import PolicyError
from proxy.policy import ConfigPolitica, _validar_ip
from proxy.schemas import (
    Manifesto,
    RequisicaoExecutor,
    RespostaExecutor,
    SondagemRequisicao,
    VerificacaoEgressRequisicao,
)

from .adapters import ADAPTADORES

_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


class ConfigExecutor:
    def __init__(self, ferramentas_dir: Optional[str] = None, token: Optional[str] = None,
                 scratch_dir: Optional[str] = None, max_concorrencia: Optional[int] = None,
                 politica: Optional[ConfigPolitica] = None):
        self.ferramentas_dir = Path(ferramentas_dir or os.environ.get("FERRAMENTAS_DIR", "/dados/ferramentas")).resolve()
        self.token = token if token is not None else os.environ.get("EXECUTOR_TOKEN", "")
        self.scratch_dir = Path(scratch_dir or os.environ.get("RESULTADOS_DIR", "/resultados"))
        self.max_concorrencia = max_concorrencia or int(os.environ.get("EXECUTOR_MAX_CONCORRENCIA", "2"))
        self.politica = politica or ConfigPolitica.from_env()


def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _limitar_recursos(cpu_s: int, fsize: int):
    def aplicar():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()
    return aplicar


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


class _Pedido(BaseModel):
    host: str


def criar_app(config: Optional[ConfigExecutor] = None) -> FastAPI:
    cfg = config or ConfigExecutor()
    app = FastAPI(title="executor", docs_url=None, redoc_url=None, openapi_url=None)
    semaforo = asyncio.Semaphore(cfg.max_concorrencia)

    def auth(x_executor_token: str = Header(default="")):
        if not cfg.token or not hmac.compare_digest(x_executor_token, cfg.token):
            raise HTTPException(status_code=401, detail="token inválido")

    @app.get("/saude")
    def saude(_: None = Depends(auth)):
        return {"ok": True, "adaptadores": sorted(ADAPTADORES)}

    @app.post("/resolver")
    def resolver(p: _Pedido, _: None = Depends(auth)):
        if not _HOST_RE.match(p.host):
            raise HTTPException(status_code=400, detail="host inválido")
        try:
            infos = socket.getaddrinfo(p.host, None, type=socket.SOCK_STREAM)
        except OSError as e:
            raise HTTPException(status_code=404, detail=f"não resolveu: {e}") from e
        ips = list(dict.fromkeys(i[4][0] for i in infos))
        return {"ips": ips}

    @app.post("/sondar")
    def sondar(req: SondagemRequisicao, _: None = Depends(auth)):
        try:
            _validar_ip(req.ip, cfg.politica)
        except PolicyError as e:
            return {"alcancavel": False, "erro": e.mensagem, "codigo": e.codigo}
        t0 = time.monotonic()
        try:
            s = socket.create_connection((req.ip, req.porta), timeout=4)
        except OSError as e:
            return {"alcancavel": False, "erro": str(e), "tempo_ms": int((time.monotonic() - t0) * 1000)}
        try:
            s.settimeout(4)
            if req.esquema == "https":
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                s = ctx.wrap_socket(s, server_hostname=req.host)
            pedido = (f"GET / HTTP/1.1\r\nHost: {req.host}\r\nUser-Agent: plataforma-sondagem\r\n"
                      f"Connection: close\r\nAccept: text/html\r\n\r\n").encode()
            s.sendall(pedido)
            dados = b""
            while len(dados) < 65536:
                bloco = s.recv(8192)
                if not bloco:
                    break
                dados += bloco
        except OSError as e:
            return {"alcancavel": True, "http": False, "erro": str(e), "tempo_ms": int((time.monotonic() - t0) * 1000)}
        finally:
            try:
                s.close()
            except OSError:
                pass
        linha = dados.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        m = re.match(r"^HTTP/[\d.]+\s+(\d{3})", linha)
        return {
            "alcancavel": True, "http": bool(m), "status": int(m.group(1)) if m else None,
            "assinatura_juice_shop": b"OWASP Juice Shop" in dados,
            "tempo_ms": int((time.monotonic() - t0) * 1000),
        }

    @app.post("/verificar-egress")
    def verificar_egress(req: VerificacaoEgressRequisicao, _: None = Depends(auth)):
        resultados = []
        for d in req.destinos:
            try:
                ipaddress.ip_address(d.ip)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"IP inválido: {d.ip}") from e
            t0 = time.monotonic()
            try:
                socket.create_connection((d.ip, d.porta), timeout=2.5).close()
                alcancou, erro = True, None
            except OSError as e:
                alcancou, erro = False, str(e)
            resultados.append({"ip": d.ip, "porta": d.porta, "rotulo": d.rotulo, "alcancou": alcancou,
                               "erro": erro, "tempo_ms": int((time.monotonic() - t0) * 1000)})
        return {"resultados": resultados}

    @app.post("/executar")
    async def executar(req: RequisicaoExecutor, _: None = Depends(auth)):
        async with semaforo:
            return (await _executar(cfg, req)).model_dump(mode="json")

    return app


def _falha(req: RequisicaoExecutor, codigo: str, msg: str, **extra: Any) -> RespostaExecutor:
    return RespostaExecutor(exec_id=req.exec_id, ok=False, erro=f"{codigo}: {msg}", **extra)


async def _executar(cfg: ConfigExecutor, req: RequisicaoExecutor) -> RespostaExecutor:
    t0 = time.monotonic()
    if not re.match(r"^[a-z0-9][a-z0-9_-]{1,39}$", req.ferramenta_id):
        return _falha(req, "ferramenta_invalida", "id inválido")
    pasta = (cfg.ferramentas_dir / req.ferramenta_id).resolve()
    if cfg.ferramentas_dir not in pasta.parents:
        return _falha(req, "ferramenta_invalida", "caminho fora da árvore de ferramentas")
    manifesto_path = pasta / "manifest.json"
    if not manifesto_path.is_file():
        return _falha(req, "ferramenta_ausente", "manifesto não encontrado")
    if _sha256_arquivo(manifesto_path) != req.manifesto_sha256:
        return _falha(req, "manifesto_alterado", "o manifesto mudou desde a revisão; nova revisão necessária")
    try:
        manifesto = Manifesto.model_validate_json(manifesto_path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as e:
        return _falha(req, "manifesto_invalido", str(e)[:300])
    adaptador = ADAPTADORES.get(manifesto.perfil)
    if adaptador is None:
        return _falha(req, "perfil_desconhecido", f"perfil {manifesto.perfil!r} sem adaptador revisado")

    exe = (pasta / manifesto.executavel).resolve()
    if pasta not in exe.parents:
        return _falha(req, "executavel_invalido", "executável fora da pasta da ferramenta")
    if not exe.is_file() or not os.access(exe, os.X_OK):
        return _falha(req, "executavel_invalido", "executável inexistente ou sem permissão de execução")
    sha_exe = _sha256_arquivo(exe)
    if sha_exe != req.executavel_sha256:
        return _falha(req, "executavel_alterado", "o executável mudou desde a revisão; nova revisão necessária",
                      executavel_sha256=sha_exe)

    try:
        _validar_ip(req.alvo.ip, cfg.politica)
        limites = manifesto.limites.model_copy(update={
            "timeout_s": min(manifesto.limites.timeout_s, cfg.politica.max_timeout_s),
            "max_saida_bytes": min(manifesto.limites.max_saida_bytes, cfg.politica.max_saida_bytes),
        })
        params = adaptador.validar(req.parametros, manifesto, req.alvo, limites, cfg.politica)
        argv = adaptador.montar_argv(str(exe), params, req.alvo, limites)
        adaptador.verificar_argv(argv, req.alvo)
    except PolicyError as e:
        return _falha(req, e.codigo, e.mensagem)

    workdir = cfg.scratch_dir / req.exec_id
    workdir.mkdir(parents=True, exist_ok=True)
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(workdir), "TMPDIR": str(workdir), "LC_ALL": "C"}
    timeout = int(params["timeout_s"])
    cap = limites.max_saida_bytes
    out, err = bytearray(), bytearray()
    estado = {"truncado": False, "timeout": False}
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir), env=env, preexec_fn=_limitar_recursos(timeout + 5, max(cap * 2, 1 << 20)),
        )

        async def ler(stream, buf):
            while True:
                bloco = await stream.read(65536)
                if not bloco:
                    return
                restante = cap - len(buf)
                if restante > 0:
                    buf.extend(bloco[:restante])
                if len(bloco) > restante:
                    estado["truncado"] = True
                    _matar(proc)
                    return

        try:
            await asyncio.wait_for(asyncio.gather(ler(proc.stdout, out), ler(proc.stderr, err), proc.wait()),
                                   timeout=timeout + 2)
        except asyncio.TimeoutError:
            estado["timeout"] = True
            _matar(proc)
            await proc.wait()
    except OSError as e:
        return _falha(req, "falha_ao_executar", str(e), argv=argv)
    finally:
        if proc is not None and proc.returncode is None:
            _matar(proc)
        shutil.rmtree(workdir, ignore_errors=True)

    codigo = proc.returncode if proc else None
    try:
        resumo = adaptador.interpretar(bytes(out), bytes(err), codigo, params, req.alvo, limites)
    except Exception as e:  # noqa: BLE001
        resumo = {"tipo": "erro_interpretacao", "erro": str(e)[:300]}
    return RespostaExecutor(
        exec_id=req.exec_id, ok=(codigo == 0 and not estado["timeout"]), argv=argv, codigo_saida=codigo,
        stdout_b64=_b64(bytes(out)), stderr_b64=_b64(bytes(err)), truncado=estado["truncado"],
        timeout=estado["timeout"], duracao_ms=int((time.monotonic() - t0) * 1000),
        erro=("tempo limite excedido" if estado["timeout"] else None), resumo=resumo, executavel_sha256=sha_exe,
    )


def _matar(proc) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


app = criar_app() if os.environ.get("EXECUTOR_TOKEN") else None
