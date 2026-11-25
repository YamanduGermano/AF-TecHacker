"""Fixtures dos testes: tudo simulado (Ollama falso, ferramentas falsas, sem rede, sem Docker)."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.app import criar_app  # noqa: E402
from agente.config import Config  # noqa: E402
from agente.ollama import ClienteOllama  # noqa: E402
from executor.service import ConfigExecutor, criar_app as criar_app_executor  # noqa: E402
from proxy.policy import ConfigPolitica  # noqa: E402
from proxy.runner import ClienteExecutor  # noqa: E402

FAKES = Path(__file__).parent / "fakes"
GGUF_FALSO = b"GGUF" + b"\x00" * 64
ALVO_IP = "192.168.1.50"
ALVO_URL = f"http://{ALVO_IP}:3000/"


class OllamaFalso:
    """Servidor Ollama simulado. `respostas` é a fila de textos que o 'modelo' devolverá."""

    def __init__(self):
        self.modelos = [{"name": "modelo-teste:1b", "digest": "a" * 64, "size": 123, "modified_at": "2026-01-01T00:00:00Z"}]
        self.respostas: list[str] = []
        self.requisicoes: list[dict] = []
        self.criados: list[dict] = []
        self.blobs: list[str] = []
        self.app = FastAPI()
        app = self.app

        @app.get("/api/tags")
        def tags():
            return {"models": self.modelos}

        @app.post("/api/show")
        async def show(req: Request):
            corpo = await req.json()
            if any(m["name"] == corpo["model"] for m in self.modelos):
                return {"modelfile": "FROM x"}
            return Response404()

        @app.post("/api/chat")
        async def chat(req: Request):
            corpo = await req.json()
            self.requisicoes.append(corpo)
            texto = self.respostas.pop(0) if self.respostas else json.dumps({"tipo": "mensagem", "texto": "(sem resposta roteirizada)"})
            return {"message": {"role": "assistant", "content": texto}}

        @app.post("/api/blobs/{digest}")
        async def blob(digest: str, req: Request):
            await req.body()
            self.blobs.append(digest)
            return {}

        @app.post("/api/create")
        async def create(req: Request):
            corpo = await req.json()
            self.criados.append(corpo)
            self.modelos.append({"name": corpo["model"], "digest": "b" * 64, "size": 1, "modified_at": "2026-01-01T00:00:00Z"})
            return {"status": "success"}


def Response404():
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"error": "model not found"})


class Plataforma:
    """Agrupa o app do agente, o executor real (ASGI em memória) e utilitários de teste."""

    def __init__(self, tmp: Path, politica: ConfigPolitica | None = None):
        self.dados = tmp / "dados"
        for d in ("modelos/ollama", "modelos/importar", "ferramentas", "documentacoes", "__shared__", "sessoes", "banco"):
            (self.dados / d).mkdir(parents=True, exist_ok=True)
        self.ollama = OllamaFalso()
        self.cfg = Config(dados_dir=self.dados, executor_token="tok-teste", turno_sincrono=True,
                          politica=politica or ConfigPolitica(), reset_url=None)
        self.executor_app = criar_app_executor(ConfigExecutor(
            ferramentas_dir=str(self.dados / "ferramentas"), token="tok-teste", scratch_dir=str(tmp / "resultados"),
            politica=self.cfg.politica))
        self.executor_http = TestClient(self.executor_app)
        self.executor = ClienteExecutor("http://executor", "tok-teste", client=self.executor_http)
        self.chamadas_executor = 0
        original = self.executor.executar

        def contado(req):
            self.chamadas_executor += 1
            return original(req)

        self.executor.executar = contado  # type: ignore[method-assign]
        self.app = criar_app(self.cfg, ollama=ClienteOllama("http://ollama", client=TestClient(self.ollama.app)),
                             executor=self.executor, varrer_na_inicializacao=False)
        self.orq = self.app.state.orq
        self.desc = self.app.state.desc
        self.arm = self.app.state.arm
        # o alvo "existe": sondagem simulada (nenhuma conexão real é feita pelos testes)
        self.orq.executor.sondar = lambda alvo: {"alcancavel": True, "http": True, "status": 200, "assinatura_juice_shop": True}  # type: ignore[method-assign]
        self.c = TestClient(self.app, headers={"X-Operador": "aluno-teste"})

    # ---- ferramentas ----
    def instalar_ferramenta(self, tid: str = "http-client", perfil: str = "http_client_curl", fake: str = "fake_curl.py",
                            doc: bool = True, manifesto_extra: dict | None = None, politica: dict | None = None) -> Path:
        pasta = self.dados / "ferramentas" / tid
        pasta.mkdir(parents=True, exist_ok=True)
        shutil.copy(FAKES / fake, pasta / "executavel")
        os.chmod(pasta / "executavel", 0o755)
        m = {"id": tid, "versao": "1.0.0", "nome": tid, "executavel": "executavel", "perfil": perfil,
             "descricao_modelo": f"Ferramenta simulada {tid} para testes automatizados",
             "limites": {"timeout_s": 5, "max_saida_bytes": 1048576, "max_corpo_bytes": 65536}}
        if politica:
            m["politica_escopo"] = politica
        if manifesto_extra:
            m.update(manifesto_extra)
        (pasta / "manifest.json").write_text(json.dumps(m))
        if doc:
            (self.dados / "documentacoes" / f"{tid}.md").write_text(f"# {tid}\nCliente simulado. Parâmetros: metodo, caminho.\n")
        return pasta

    def habilitar(self, tid: str = "http-client") -> dict:
        f = self.desc.ferramenta(tid)
        r = self.c.post(f"/api/ferramentas/{tid}/habilitar", json={"manifesto_sha256": f["manifesto_sha256"], "justificativa": "revisado no teste"})
        assert r.status_code == 200, r.text
        return r.json()

    def ferramenta_pronta(self, tid: str = "http-client", **kw) -> Path:
        pasta = self.instalar_ferramenta(tid, **kw)
        self.habilitar(tid)
        return pasta

    # ---- sessão ----
    def sessao(self, plano: bool = True, modelo: bool = True, **kw) -> str:
        if modelo:
            assert self.c.post("/api/modelos/selecionar", json={"modelo_id": "modelo-teste:1b"}).status_code == 200
        corpo = {"nome": "Sessão de teste", "objetivo": "Observar o Juice Shop de laboratório", "modo": "lan", "url": ALVO_URL,
                 "confirmou_autorizacao": True}
        corpo.update(kw)
        r = self.c.post("/api/sessoes", json=corpo)
        assert r.status_code == 200, r.text
        sid = r.json()["sessao"]["id"]
        if plano:
            self.plano(sid)
        return sid

    def plano(self, sid: str):
        r = self.c.post(f"/api/sessoes/{sid}/plano", json={
            "aspectos": "Catálogo de produtos e busca", "hipoteses": "A busca pode refletir a entrada",
            "estrategia": "Observar respostas antes de qualquer variação", "ferramentas": "http-client",
            "evidencias_esperadas": "Resposta HTTP bruta registrada"})
        assert r.status_code == 200, r.text

    def investigar(self, sid: str, resposta_modelo: dict | str):
        self.ollama.respostas.append(resposta_modelo if isinstance(resposta_modelo, str) else json.dumps(resposta_modelo))
        r = self.c.post(f"/api/sessoes/{sid}/investigacoes", json={"titulo": "Busca de produtos", "hipotese": "Observar a API de busca"})
        assert r.status_code == 200, r.text
        return r.json()

    def estado(self, sid: str) -> dict:
        return self.c.get(f"/api/sessoes/{sid}").json()


def proposta(caminho="/rest/products/search?q=apple", **extra) -> dict:
    p = {"tipo": "proposta", "ferramenta": "http-client", "parametros": {"metodo": "GET", "caminho": caminho},
         "justificativa": "Observar a resposta da busca antes de qualquer variação"}
    p.update(extra)
    return p


@pytest.fixture
def plat(tmp_path) -> Plataforma:
    return Plataforma(tmp_path)


@pytest.fixture
def mk(tmp_path):
    def fabrica(politica: ConfigPolitica | None = None) -> Plataforma:
        return Plataforma(tmp_path, politica)
    return fabrica
