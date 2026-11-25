"""API do agente (FastAPI): sessões, aprovações, catálogo, exportação.

Iniciar com:  uvicorn agente.app:criar_app --factory --host 0.0.0.0 --port 8000
A API não é publicada pelo Docker: apenas o ``web-ui`` (nginx) a alcança, pela rede interna.
"""
from __future__ import annotations

import base64
import re
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from proxy.params import PolicyError
from proxy.runner import ClienteExecutor

from .config import Config
from .discovery import Descoberta
from .ollama import ClienteOllama
from .orchestrator import ErroNegocio, Orquestrador
from .reports import gerar_rascunho, salvar_rascunho
from .storage import Armazenamento, redigir_obj, redigir_texto

INSTRUCOES = {
    "modelos": [
        "Opção A — registrar pelo Ollama usando o mesmo armazenamento persistente: "
        "`docker compose -f compose.yaml -f compose.pull.yaml run --rm ollama-pull ollama pull <modelo>` "
        "(o arquivo compose.pull.yaml dá acesso à internet apenas a esse comando).",
        "Opção B — GGUF local: copie `arquivo.gguf` e `arquivo.Modelfile` (com `FROM arquivo.gguf`) para dados/modelos/importar/, "
        "clique em «Verificar novos recursos» e depois em «Importar» no catálogo de modelos.",
        "Depois da varredura, selecione o modelo. Só aparecem como utilizáveis os modelos registrados e validados pela API do Ollama.",
    ],
    "ferramentas": [
        "Crie dados/ferramentas/<id>/ com `manifest.json` e o executável fornecido por você (chmod +x).",
        "Coloque a documentação em dados/documentacoes/<id>.md (propósito, exemplos, parâmetros, interpretação dos resultados).",
        "Veja exemplos de manifesto em exemplos/ferramentas/ (não executáveis). Perfis aceitos: http_client_curl, port_scanner_nmap.",
        "Clique em «Verificar novos recursos», revise manifesto e política e habilite a ferramenta. Alterações posteriores a suspendem.",
    ],
}


class Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AlvoIn(Estrito):
    modo: str
    url: Optional[str] = Field(default=None, max_length=300)
    confirmou_autorizacao: bool = False
    portas_autorizadas_extra: list[int] = Field(default_factory=list, max_length=9)


class SessaoIn(AlvoIn):
    nome: str = Field(max_length=120)
    objetivo: str = Field(max_length=2000)
    modelo_id: Optional[str] = Field(default=None, max_length=100)


class EscopoIn(AlvoIn):
    justificativa: str = Field(max_length=1000)


class PlanoIn(Estrito):
    aspectos: str = ""
    hipoteses: str = ""
    estrategia: str = ""
    ferramentas: str = ""
    evidencias_esperadas: str = ""


class MensagemIn(Estrito):
    texto: str = Field(max_length=4000)


class InvestigacaoIn(Estrito):
    titulo: str = Field(max_length=200)
    hipotese: str = Field(max_length=2000)
    estrategia: str = Field(default="", max_length=2000)


class EncerrarIn(Estrito):
    conclusao: str = Field(default="", max_length=4000)
    limites: str = Field(default="", max_length=4000)


class SugestaoDecisaoIn(Estrito):
    decisao: str
    justificativa: str = Field(max_length=2000)
    texto_alterado: Optional[str] = Field(default=None, max_length=2000)


class DecisaoAcaoIn(Estrito):
    decisao: str
    justificativa: Optional[str] = Field(default=None, max_length=2000)
    parametros_editados: Optional[dict[str, Any]] = None


class NotaIn(Estrito):
    texto: str = Field(max_length=4000)


class EvidenciaIn(Estrito):
    acao_id: Optional[str] = Field(default=None, max_length=30)
    resultado_id: Optional[str] = Field(default=None, max_length=30)
    nota: str = Field(max_length=2000)


class InterromperIn(Estrito):
    motivo: Optional[str] = Field(default=None, max_length=500)


class ResetIn(Estrito):
    confirmacao: bool = False
    procedimento: Optional[str] = Field(default=None, max_length=2000)


class ModeloSessaoIn(Estrito):
    modelo_id: str = Field(max_length=100)
    reiniciar_contexto: bool = False


class ModeloSelecionarIn(Estrito):
    modelo_id: str = Field(max_length=100)


class ModeloImportarIn(Estrito):
    arquivo: str = Field(max_length=200)
    nome: str = Field(max_length=64)


class HabilitarIn(Estrito):
    manifesto_sha256: str = Field(min_length=64, max_length=64)
    justificativa: Optional[str] = Field(default=None, max_length=1000)


class EgressIn(Estrito):
    sessao_id: Optional[str] = None
    destinos_extra: list[str] = Field(default_factory=list, max_length=5)


class RelatorioIn(Estrito):
    conteudo: str = Field(max_length=500_000)


def _operador(x_operador: str = Header(default="")) -> str:
    return re.sub(r"[^\w .@-]", "", x_operador)[:60].strip() or "operador"


def criar_app(cfg: Optional[Config] = None, *, ollama: Optional[ClienteOllama] = None,
              executor: Optional[ClienteExecutor] = None, varrer_na_inicializacao: bool = True) -> FastAPI:
    cfg = cfg or Config.from_env()
    arm = Armazenamento(cfg.dados_dir)
    ollama = ollama or ClienteOllama(cfg.ollama_url, timeout_s=cfg.ollama_timeout_s, temperatura=cfg.ollama_temperatura)
    executor = executor or ClienteExecutor(cfg.executor_url, cfg.executor_token)
    desc = Descoberta(cfg, arm, ollama)
    orq = Orquestrador(cfg, arm, desc, ollama, executor)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if varrer_na_inicializacao:
            desc.iniciar_varredura(sincrona=False)
        yield

    app = FastAPI(title="agente", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.orq, app.state.desc, app.state.arm, app.state.cfg = orq, desc, arm, cfg

    @app.exception_handler(ErroNegocio)
    async def _h_negocio(_: Request, e: ErroNegocio):
        return JSONResponse(status_code=e.status, content={"codigo": e.codigo, "mensagem": e.mensagem, "detalhes": e.detalhes})

    @app.exception_handler(PolicyError)
    async def _h_politica(_: Request, e: PolicyError):
        return JSONResponse(status_code=422, content={"codigo": e.codigo, "mensagem": e.mensagem, "detalhes": e.detalhes})

    # ------------------------------ plataforma ------------------------------ #
    @app.get("/api/saude")
    def saude():
        return {"ok": True}

    @app.get("/api/estado")
    def estado():
        ferr = desc.ferramentas()
        modelos = [r["dados"] for r in arm.catalogo("modelo")]
        ativos = [m for m in modelos if m["tipo"] == "registrado" and m["estado"] == "disponivel"]
        ultimo = arm.ajuste("ultimo_egress")
        import json as _json
        return redigir_obj({
            "ollama_acessivel": ollama.saude(), "executor_acessivel": executor.saude(),
            "modelo_ativo": arm.ajuste("modelo_ativo"),
            "modelos": modelos, "ferramentas": ferr,
            "sem_modelos": not ativos, "sem_ferramentas": not any(f["utilizavel"] for f in ferr),
            "instrucoes": INSTRUCOES, "ultima_varredura": desc.ultima_varredura(),
            "egress": _json.loads(ultimo) if ultimo else None,
            "limites": {"max_passos": cfg.politica.max_passos_por_investigacao, "max_chamadas_minuto": cfg.politica.max_chamadas_por_minuto,
                        "metodos_permitidos": sorted(cfg.politica.metodos_permitidos)},
            "sessoes": [{"id": s["id"], "nome": s["nome"], "fase": s["fase"], "estado": s["estado"], "criado_em": s["criado_em"]}
                        for s in arm.listar_sessoes()],
        })

    @app.post("/api/varreduras")
    def iniciar_varredura(op: str = Depends(_operador)):
        v = desc.iniciar_varredura(sincrona=cfg.turno_sincrono)
        return redigir_obj(v)

    @app.get("/api/varreduras/{vid}")
    def ver_varredura(vid: str):
        v = desc.varredura(vid)
        if v is None:
            raise ErroNegocio(404, "varredura_inexistente", "varredura não encontrada")
        return redigir_obj(v)

    @app.post("/api/modelos/selecionar")
    def selecionar_modelo(b: ModeloSelecionarIn, op: str = Depends(_operador)):
        m = desc.modelo_disponivel(b.modelo_id)
        if m is None:
            raise ErroNegocio(422, "modelo_indisponivel", "modelo não registrado/validado no Ollama")
        arm.definir_ajuste("modelo_ativo", b.modelo_id)
        arm.registrar_evento(None, "modelo_ativo_alterado", {"modelo_id": b.modelo_id, "digest": m["digest"], "operador": op,
                                                             "nota": "vale para novas sessões; sessões existentes não migram"})
        return {"modelo_ativo": b.modelo_id}

    @app.post("/api/modelos/importar")
    def importar_modelo(b: ModeloImportarIn, op: str = Depends(_operador)):
        r = desc.importar_modelo(b.arquivo, b.nome, op)
        desc.iniciar_varredura(sincrona=True)
        return r

    @app.get("/api/ferramentas/{tid}")
    def ver_ferramenta(tid: str):
        f = desc.ferramenta(tid)
        if f is None:
            raise ErroNegocio(404, "ferramenta_inexistente", "ferramenta não encontrada")
        doc = None
        if f.get("documentacao"):
            p = (cfg.documentacoes_dir / f["documentacao"])
            if p.is_file():
                doc = p.read_text(encoding="utf-8", errors="replace")[:20000]
        return redigir_obj({**f, "documentacao_texto": doc})

    @app.post("/api/ferramentas/{tid}/habilitar")
    def habilitar(tid: str, b: HabilitarIn, op: str = Depends(_operador)):
        return redigir_obj(desc.habilitar(tid, manifesto_sha256=b.manifesto_sha256, operador=op, justificativa=b.justificativa))

    @app.post("/api/ferramentas/{tid}/desabilitar")
    def desabilitar(tid: str, op: str = Depends(_operador)):
        desc.desabilitar(tid, op)
        return {"ok": True}

    @app.post("/api/alvo/validar")
    def validar_alvo(b: AlvoIn):
        return orq.validar_alvo(b.modo, b.url, b.confirmou_autorizacao, b.portas_autorizadas_extra)

    @app.post("/api/egress/verificar")
    def egress(b: EgressIn):
        return orq.verificar_egress(b.sessao_id, b.destinos_extra)

    # ------------------------------ sessões ------------------------------ #
    @app.post("/api/sessoes")
    def criar_sessao(b: SessaoIn, op: str = Depends(_operador)):
        return orq.criar_sessao(nome=b.nome, objetivo=b.objetivo, modo=b.modo, url=b.url,
                                confirmou_autorizacao=b.confirmou_autorizacao, portas_extra=b.portas_autorizadas_extra,
                                modelo_id=b.modelo_id, operador=op)

    @app.get("/api/sessoes/{sid}")
    def ver_sessao(sid: str):
        return orq.estado_sessao(sid)

    @app.post("/api/sessoes/{sid}/modelo")
    def trocar_modelo(sid: str, b: ModeloSessaoIn, op: str = Depends(_operador)):
        return orq.definir_modelo_sessao(sid, b.modelo_id, b.reiniciar_contexto, op)

    @app.post("/api/sessoes/{sid}/escopo")
    def redefinir_escopo(sid: str, b: EscopoIn, op: str = Depends(_operador)):
        return orq.redefinir_escopo(sid, url=b.url, modo=b.modo, confirmou=b.confirmou_autorizacao,
                                    portas_extra=b.portas_autorizadas_extra, justificativa=b.justificativa, operador=op)

    @app.post("/api/sessoes/{sid}/plano")
    def salvar_plano(sid: str, b: PlanoIn, op: str = Depends(_operador)):
        return orq.salvar_plano(sid, b.model_dump(), op)

    @app.post("/api/sessoes/{sid}/iniciar")
    def iniciar(sid: str, op: str = Depends(_operador)):
        return orq.consultar_plano(sid, op)

    @app.post("/api/sessoes/{sid}/mensagens")
    def mensagem(sid: str, b: MensagemIn, op: str = Depends(_operador)):
        return orq.enviar_mensagem(sid, b.texto, op)

    @app.get("/api/sessoes/{sid}/chat")
    def chat(sid: str, desde: int = Query(default=0, ge=0)):
        orq._sessao(sid)
        linhas = arm._todos("SELECT * FROM mensagens WHERE sessao_id=? AND seq>? ORDER BY seq", (sid, desde))
        return redigir_obj({"mensagens": linhas, "ultima_seq": arm.ultima_seq_mensagem(sid)})

    @app.get("/api/sessoes/{sid}/eventos")
    def eventos(sid: str, investigacao: Optional[str] = None):
        orq._sessao(sid)
        return redigir_obj({"eventos": arm.eventos(sid, investigacao)})

    @app.get("/api/sessoes/{sid}/acoes")
    def acoes(sid: str):
        orq._sessao(sid)
        return redigir_obj({"acoes": arm.acoes(sid)})

    @app.post("/api/sessoes/{sid}/investigacoes")
    def iniciar_investigacao(sid: str, b: InvestigacaoIn, op: str = Depends(_operador)):
        return orq.iniciar_investigacao(sid, b.titulo, b.hipotese, b.estrategia, op)

    @app.post("/api/sessoes/{sid}/investigacoes/{numero}/encerrar")
    def encerrar_investigacao(sid: str, numero: int, b: EncerrarIn, op: str = Depends(_operador)):
        return orq.encerrar_investigacao(sid, numero, b.conclusao, b.limites, op)

    @app.post("/api/sessoes/{sid}/sugestoes/{gid}/decisao")
    def decidir_sugestao(sid: str, gid: str, b: SugestaoDecisaoIn, op: str = Depends(_operador)):
        return redigir_obj(orq.decidir_sugestao(sid, gid, b.decisao, b.justificativa, b.texto_alterado, op))

    @app.post("/api/sessoes/{sid}/interromper")
    def interromper(sid: str, b: InterromperIn, op: str = Depends(_operador)):
        return orq.interromper(sid, b.motivo, op)

    @app.post("/api/sessoes/{sid}/reset")
    def reset(sid: str, b: ResetIn, op: str = Depends(_operador)):
        return redigir_obj(orq.resetar_alvo(sid, confirmacao=b.confirmacao, procedimento=b.procedimento, operador=op))

    @app.post("/api/sessoes/{sid}/evidencias")
    def evidencia(sid: str, b: EvidenciaIn, op: str = Depends(_operador)):
        return redigir_obj(orq.criar_evidencia(sid, acao_id=b.acao_id, resultado_id=b.resultado_id, nota=b.nota, operador=op))

    # ------------------------------ ações ------------------------------ #
    @app.get("/api/acoes/{aid}")
    def ver_acao(aid: str):
        a = arm.acao(aid)
        if a is None:
            raise ErroNegocio(404, "acao_inexistente", "ação não encontrada")
        return redigir_obj(a)

    @app.post("/api/acoes/{aid}/decisao")
    def decidir(aid: str, b: DecisaoAcaoIn, op: str = Depends(_operador)):
        return redigir_obj(orq.decidir_acao(aid, b.decisao, b.justificativa, b.parametros_editados, op))

    @app.post("/api/acoes/{aid}/nota")
    def nota(aid: str, b: NotaIn, op: str = Depends(_operador)):
        return redigir_obj(orq.registrar_nota_acao(aid, b.texto, op))

    @app.get("/api/acoes/{aid}/saida")
    def saida(aid: str):
        a = arm.acao(aid)
        if a is None:
            raise ErroNegocio(404, "acao_inexistente", "ação não encontrada")
        out: dict[str, Any] = {}
        for rid in a.get("resultado_ids") or []:
            r, dados = arm.ler_resultado(rid)
            out[r["nome"]] = {"id": r["id"], "sha256": r["sha256"], "tamanho": r["tamanho"],
                              "texto": redigir_texto(dados[:200_000].decode("utf-8", errors="replace")),
                              "cortado": len(dados) > 200_000}
        return out

    # ------------------------------ exportação e relatório ------------------------------ #
    @app.get("/api/sessoes/{sid}/exportar/{item}")
    def exportar(sid: str, item: str):
        orq._sessao(sid)
        zipmime = "application/zip"
        if item == "chat":
            return _anexo(arm.exportar_texto(sid, "chat.jsonl"), f"{sid}-chat.jsonl", "application/x-ndjson")
        if item == "eventos":
            return _anexo(arm.exportar_texto(sid, "eventos.jsonl"), f"{sid}-eventos.jsonl", "application/x-ndjson")
        if item == "relatorio":
            texto = arm.exportar_texto(sid, "relatorio.md") or gerar_rascunho(arm, sid).encode()
            return _anexo(texto, f"{sid}-relatorio.md", "text/markdown")
        if item == "arquivos":
            return _anexo(arm.exportar_zip(sid, ("plano", "eventos.jsonl", "chat.jsonl", "consultas-modelo.jsonl", "evidencias/", "relatorio")),
                          f"{sid}-arquivos.zip", zipmime)
        if item == "resultados":
            return _anexo(arm.exportar_zip(sid, ("resultados-ferramentas/",)), f"{sid}-resultados.zip", zipmime)
        if item == "completo":
            return _anexo(arm.exportar_zip(sid, ("",)), f"{sid}-completo.zip", zipmime)
        raise ErroNegocio(404, "item_desconhecido", "itens: chat, eventos, arquivos, resultados, relatorio, completo")

    @app.get("/api/sessoes/{sid}/relatorio")
    def ver_relatorio(sid: str):
        orq._sessao(sid)
        p = arm.dir_sessao(sid) / "relatorio.md"
        return {"existe": p.exists(), "conteudo": redigir_texto(p.read_text(encoding="utf-8")) if p.exists() else gerar_rascunho(arm, sid)}

    @app.post("/api/sessoes/{sid}/relatorio/gerar")
    def gerar_relatorio(sid: str, sobrescrever: bool = False):
        orq._sessao(sid)
        texto, gravou = salvar_rascunho(arm, sid, sobrescrever)
        if not gravou:
            raise ErroNegocio(409, "relatorio_existente", "já existe um relatório editado; use sobrescrever=true (o anterior é preservado como .bak)")
        return {"conteudo": texto}

    @app.put("/api/sessoes/{sid}/relatorio")
    def salvar_relatorio(sid: str, b: RelatorioIn, op: str = Depends(_operador)):
        orq._sessao(sid)
        p = arm.dir_sessao(sid) / "relatorio.md"
        if p.exists():
            from .storage import agora
            p.replace(p.with_name(f"relatorio.bak-{agora().replace(':', '').replace('.', '')}.md"))
        p.write_text(b.conteudo, encoding="utf-8")
        arm.registrar_evento(sid, "relatorio_editado", {"operador": op, "tamanho": len(b.conteudo)})
        return {"ok": True}

    return app


def _anexo(dados: bytes, nome: str, mime: str) -> Response:
    return Response(content=dados, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{nome}"',
                                                             "X-Content-Type-Options": "nosniff"})
