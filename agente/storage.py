"""Armazenamento: SQLite (sessões e metadados) + arquivos por sessão (logs e evidências).

Resultados brutos de ferramentas são gravados **uma única vez** (``O_EXCL``), em modo somente
leitura, com nome seguro, tamanho e SHA-256. Eventos recebem identificador e vínculo com o
evento anterior da mesma sessão.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SESSAO_ID_RE = re.compile(r"^s-[0-9a-f]{10}$")
NOME_SEGURO_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def novo_id(prefixo: str) -> str:
    return f"{prefixo}-{uuid.uuid4().hex[:10]}"


# --------------------------------------------------------------------------- #
# Redação de credenciais (interface e exportações). O registro interno é preservado.
# --------------------------------------------------------------------------- #
# (\\?") captura a aspa — escapada ou não — e \1 a reaproveita, para que o JSON continue válido
# mesmo quando o valor está dentro de uma string JSON (ex.: conteúdo de chat.jsonl).
_PADROES_REDACAO = [
    (re.compile(r"(?i)\b(authorization|cookie|set-cookie|x-api-key|proxy-authorization)\s*:\s*[^\r\n\"\\]+"), r"\1: [REDIGIDO]"),
    (re.compile(r'(?i)(\\?")(authorization|cookie|set-cookie|x-api-key)\1\s*:\s*\1[^"\\]*\1'), r'\1\2\1: \1[REDIGIDO]\1'),
    (re.compile(r'(?i)\[\s*(\\?")(authorization|cookie|set-cookie|x-api-key)\1\s*,\s*\1[^"\\]*\1\s*\]'), r'[\1\2\1, \1[REDIGIDO]\1]'),
    (re.compile(r'(?i)(\\?")(token|access_token|refresh_token|password|senha|jwt|authentication)\1\s*:\s*\1[^"\\]*\1'), r'\1\2\1: \1[REDIGIDO]\1'),
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"), "[JWT-REDIGIDO]"),
]


def redigir_texto(texto: str) -> str:
    for padrao, subst in _PADROES_REDACAO:
        texto = padrao.sub(subst, texto)
    return texto


def redigir_obj(obj: Any) -> Any:
    return json.loads(redigir_texto(json.dumps(obj, ensure_ascii=False)))


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


_ESQUEMA = """
CREATE TABLE IF NOT EXISTS sessoes (
  id TEXT PRIMARY KEY, nome TEXT NOT NULL, objetivo TEXT NOT NULL, modo TEXT NOT NULL,
  escopo_json TEXT NOT NULL, modelo_id TEXT, modelo_digest TEXT, fase TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'ativa', bloqueios_consecutivos INTEGER NOT NULL DEFAULT 0,
  investigacao_ativa_id TEXT, contexto_desde_msg INTEGER NOT NULL DEFAULT 0,
  operador TEXT, criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL, ultimo_reset_em TEXT, aviso TEXT
);
CREATE TABLE IF NOT EXISTS planos (
  id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL, versao INTEGER NOT NULL, conteudo_json TEXT NOT NULL,
  operador TEXT, criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS investigacoes (
  id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL, numero INTEGER NOT NULL, titulo TEXT NOT NULL,
  hipotese TEXT, estrategia TEXT, estado TEXT NOT NULL, conclusao TEXT, limites_texto TEXT,
  criado_em TEXT NOT NULL, encerrada_em TEXT
);
CREATE TABLE IF NOT EXISTS acoes (
  id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL, investigacao_id TEXT, estado TEXT NOT NULL,
  ferramenta_id TEXT, proposta_json TEXT, parametros_originais_json TEXT, parametros_efetivos_json TEXT,
  acao_json TEXT, decisao TEXT, justificativa TEXT, operador TEXT, validacao_json TEXT,
  execucao_json TEXT, resumo_json TEXT, resultado_ids_json TEXT, hashes_json TEXT,
  criado_em TEXT NOT NULL, decidido_em TEXT, executado_em TEXT
);
CREATE TABLE IF NOT EXISTS eventos (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, sessao_id TEXT, investigacao_id TEXT,
  ts TEXT NOT NULL, tipo TEXT NOT NULL, objetivo TEXT, anterior_id TEXT, dados_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_eventos_sessao ON eventos(sessao_id, seq);
CREATE TABLE IF NOT EXISTS mensagens (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, sessao_id TEXT NOT NULL, investigacao_id TEXT,
  acao_id TEXT, ts TEXT NOT NULL, papel TEXT NOT NULL, conteudo TEXT NOT NULL, meta_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_msg_sessao ON mensagens(sessao_id, seq);
CREATE TABLE IF NOT EXISTS consultas (
  id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL, ts TEXT NOT NULL, modelo_id TEXT, modelo_digest TEXT,
  mensagens_json TEXT, resposta TEXT, duracao_ms INTEGER, erro TEXT
);
CREATE TABLE IF NOT EXISTS sugestoes (
  id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL, ts TEXT NOT NULL, item TEXT, texto TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'pendente', justificativa TEXT, texto_alterado TEXT, operador TEXT, decidido_em TEXT
);
CREATE TABLE IF NOT EXISTS resultados (
  id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL, acao_id TEXT NOT NULL, nome TEXT NOT NULL,
  arquivo TEXT NOT NULL, tamanho INTEGER NOT NULL, sha256 TEXT NOT NULL, criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidencias (
  id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL, investigacao_id TEXT, resultado_id TEXT, acao_id TEXT,
  nota TEXT NOT NULL, operador TEXT, criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS habilitacoes (
  ferramenta_id TEXT PRIMARY KEY, manifesto_sha256 TEXT NOT NULL, executavel_sha256 TEXT NOT NULL,
  doc_sha256 TEXT, operador TEXT, justificativa TEXT, habilitado_em TEXT NOT NULL, ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS catalogo (
  tipo TEXT NOT NULL, rid TEXT NOT NULL, hash TEXT, estado TEXT, dados_json TEXT NOT NULL,
  visto_em TEXT NOT NULL, removido_em TEXT, PRIMARY KEY (tipo, rid)
);
CREATE TABLE IF NOT EXISTS varreduras (
  id TEXT PRIMARY KEY, iniciada_em TEXT NOT NULL, concluida_em TEXT, estado TEXT NOT NULL, dados_json TEXT
);
CREATE TABLE IF NOT EXISTS ajustes (chave TEXT PRIMARY KEY, valor TEXT);
"""


class Armazenamento:
    def __init__(self, dados_dir: Path):
        self.dados = Path(dados_dir)
        self.sessoes_dir = self.dados / "sessoes"
        self.banco_dir = self.dados / "banco"
        self.sessoes_dir.mkdir(parents=True, exist_ok=True)
        self.banco_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.banco_dir / "plataforma.sqlite3", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_ESQUEMA)
            self._conn.commit()
        self._colunas: dict[str, list[str]] = {}

    # ---------------- utilidades de banco ---------------- #
    def _cols(self, tabela: str) -> list[str]:
        if tabela not in self._colunas:
            self._colunas[tabela] = [r["name"] for r in self._conn.execute(f"PRAGMA table_info({tabela})")]
        return self._colunas[tabela]

    def _mapear(self, tabela: str, dados: dict[str, Any]) -> dict[str, Any]:
        cols = set(self._cols(tabela))
        saida: dict[str, Any] = {}
        for k, v in dados.items():
            if k in cols:
                saida[k] = v
            elif f"{k}_json" in cols:
                saida[f"{k}_json"] = json.dumps(v, ensure_ascii=False)
            else:
                raise KeyError(f"coluna desconhecida {tabela}.{k}")
        return saida

    @staticmethod
    def _linha(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        d: dict[str, Any] = {}
        for k in row.keys():
            v = row[k]
            if k.endswith("_json"):
                d[k[:-5]] = json.loads(v) if v else None
            else:
                d[k] = v
        return d

    def _inserir(self, tabela: str, dados: dict[str, Any]) -> None:
        m = self._mapear(tabela, dados)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {tabela} ({','.join(m)}) VALUES ({','.join('?' * len(m))})", list(m.values()))
            self._conn.commit()

    def _atualizar(self, tabela: str, chave: str, valor: Any, dados: dict[str, Any]) -> None:
        m = self._mapear(tabela, dados)
        if not m:
            return
        with self._lock:
            self._conn.execute(
                f"UPDATE {tabela} SET {','.join(f'{k}=?' for k in m)} WHERE {chave}=?", [*m.values(), valor])
            self._conn.commit()

    def _um(self, sql: str, params: tuple = ()) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._linha(self._conn.execute(sql, params).fetchone())

    def _todos(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [self._linha(r) for r in self._conn.execute(sql, params).fetchall()]  # type: ignore[misc]

    # ---------------- diretórios da sessão ---------------- #
    def dir_sessao(self, sessao_id: str) -> Path:
        if not SESSAO_ID_RE.match(sessao_id):
            raise ValueError("id de sessão inválido")
        d = (self.sessoes_dir / sessao_id).resolve()
        if self.sessoes_dir.resolve() not in d.parents:
            raise ValueError("caminho fora de sessoes/")
        return d

    def _anexar_jsonl(self, caminho: Path, obj: dict[str, Any]) -> None:
        with self._lock, open(caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # ---------------- ajustes ---------------- #
    def ajuste(self, chave: str, padrao: Optional[str] = None) -> Optional[str]:
        r = self._um("SELECT valor FROM ajustes WHERE chave=?", (chave,))
        return r["valor"] if r else padrao

    def definir_ajuste(self, chave: str, valor: Optional[str]) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO ajustes(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                               (chave, valor))
            self._conn.commit()

    # ---------------- sessões ---------------- #
    def criar_sessao(self, *, nome: str, objetivo: str, modo: str, escopo: dict, modelo_id: Optional[str],
                     modelo_digest: Optional[str], operador: Optional[str]) -> dict[str, Any]:
        sid = f"s-{uuid.uuid4().hex[:10]}"
        d = self.dir_sessao(sid)
        (d / "evidencias").mkdir(parents=True, exist_ok=True)
        (d / "resultados-ferramentas").mkdir(parents=True, exist_ok=True)
        t = agora()
        self._inserir("sessoes", {
            "id": sid, "nome": nome, "objetivo": objetivo, "modo": modo, "escopo": escopo, "modelo_id": modelo_id,
            "modelo_digest": modelo_digest, "fase": "aguardando_plano", "estado": "ativa", "operador": operador,
            "criado_em": t, "atualizado_em": t,
        })
        return self.sessao(sid)  # type: ignore[return-value]

    def sessao(self, sessao_id: str) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM sessoes WHERE id=?", (sessao_id,))

    def listar_sessoes(self) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM sessoes ORDER BY criado_em DESC")

    def atualizar_sessao(self, sessao_id: str, **campos: Any) -> None:
        campos["atualizado_em"] = agora()
        self._atualizar("sessoes", "id", sessao_id, campos)

    # ---------------- planos ---------------- #
    @staticmethod
    def plano_markdown(plano: dict[str, Any], versao: int, ts: str, sessao: dict[str, Any]) -> str:
        rot = [("aspectos", "Aspectos da aplicação a investigar"), ("hipoteses", "Hipóteses iniciais"),
               ("estrategia", "Estratégia"), ("ferramentas", "Ferramentas previstas"),
               ("evidencias_esperadas", "Evidências esperadas")]
        linhas = [f"# Plano humano — {sessao['nome']}", "", f"- Versão: {versao}", f"- Data (UTC): {ts}",
                  f"- Alvo: {sessao['escopo'].get('url_base')}", f"- Objetivo: {sessao['objetivo']}", ""]
        for k, titulo in rot:
            linhas += [f"## {titulo}", "", str(plano.get(k, "")).strip() or "_(vazio)_", ""]
        return "\n".join(linhas)

    def salvar_plano(self, sessao_id: str, conteudo: dict[str, Any], operador: Optional[str]) -> dict[str, Any]:
        sessao = self.sessao(sessao_id)
        assert sessao
        anterior = self._um("SELECT MAX(versao) AS v FROM planos WHERE sessao_id=?", (sessao_id,))
        versao = int((anterior or {}).get("v") or 0) + 1
        t = agora()
        pid = novo_id("p")
        self._inserir("planos", {"id": pid, "sessao_id": sessao_id, "versao": versao, "conteudo": conteudo,
                                 "operador": operador, "criado_em": t})
        nome = "plano-inicial.md" if versao == 1 else f"plano-v{versao}.md"
        caminho = self.dir_sessao(sessao_id) / nome
        with open(caminho, "x", encoding="utf-8") as f:   # nunca sobrescreve versões anteriores
            f.write(self.plano_markdown(conteudo, versao, t, sessao))
        return {"id": pid, "versao": versao, "criado_em": t, "arquivo": nome}

    def plano_atual(self, sessao_id: str) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM planos WHERE sessao_id=? ORDER BY versao DESC LIMIT 1", (sessao_id,))

    def planos(self, sessao_id: str) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM planos WHERE sessao_id=? ORDER BY versao", (sessao_id,))

    # ---------------- investigações ---------------- #
    def criar_investigacao(self, sessao_id: str, titulo: str, hipotese: str, estrategia: str) -> dict[str, Any]:
        r = self._um("SELECT COUNT(*) AS n FROM investigacoes WHERE sessao_id=?", (sessao_id,))
        numero = int(r["n"]) + 1  # type: ignore[index]
        iid = novo_id("i")
        self._inserir("investigacoes", {"id": iid, "sessao_id": sessao_id, "numero": numero, "titulo": titulo,
                                        "hipotese": hipotese, "estrategia": estrategia, "estado": "ativa",
                                        "criado_em": agora()})
        return self.investigacao(iid)  # type: ignore[return-value]

    def investigacao(self, iid: str) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM investigacoes WHERE id=?", (iid,))

    def investigacoes(self, sessao_id: str) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM investigacoes WHERE sessao_id=? ORDER BY numero", (sessao_id,))

    def atualizar_investigacao(self, iid: str, **campos: Any) -> None:
        self._atualizar("investigacoes", "id", iid, campos)

    # ---------------- ações ---------------- #
    def criar_acao(self, **dados: Any) -> dict[str, Any]:
        aid = novo_id("a")
        dados.setdefault("criado_em", agora())
        self._inserir("acoes", {"id": aid, **dados})
        return self.acao(aid)  # type: ignore[return-value]

    def acao(self, aid: str) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM acoes WHERE id=?", (aid,))

    def acoes(self, sessao_id: str, investigacao_id: Optional[str] = None) -> list[dict[str, Any]]:
        if investigacao_id:
            return self._todos("SELECT * FROM acoes WHERE sessao_id=? AND investigacao_id=? ORDER BY criado_em",
                               (sessao_id, investigacao_id))
        return self._todos("SELECT * FROM acoes WHERE sessao_id=? ORDER BY criado_em", (sessao_id,))

    def acao_pendente(self, sessao_id: str) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM acoes WHERE sessao_id=? AND estado IN ('pendente','executando') "
                        "ORDER BY criado_em DESC LIMIT 1", (sessao_id,))

    def contar_acoes(self, investigacao_id: str) -> int:
        r = self._um("SELECT COUNT(*) AS n FROM acoes WHERE investigacao_id=?", (investigacao_id,))
        return int(r["n"])  # type: ignore[index]

    def atualizar_acao(self, aid: str, **campos: Any) -> None:
        self._atualizar("acoes", "id", aid, campos)

    # ---------------- eventos / chat ---------------- #
    def registrar_evento(self, sessao_id: Optional[str], tipo: str, dados: dict[str, Any], *,
                         investigacao_id: Optional[str] = None, objetivo: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            ant = self._conn.execute(
                "SELECT id FROM eventos WHERE sessao_id IS ? ORDER BY seq DESC LIMIT 1", (sessao_id,)).fetchone()
            evento = {"id": novo_id("e"), "sessao_id": sessao_id, "investigacao_id": investigacao_id, "ts": agora(),
                      "tipo": tipo, "objetivo": objetivo, "anterior_id": ant["id"] if ant else None, "dados": dados}
            self._inserir("eventos", evento)
        destino = (self.dir_sessao(sessao_id) / "eventos.jsonl") if sessao_id else (self.banco_dir / "eventos-sistema.jsonl")
        self._anexar_jsonl(destino, evento)
        return evento

    def eventos(self, sessao_id: Optional[str], investigacao_id: Optional[str] = None) -> list[dict[str, Any]]:
        if investigacao_id:
            return self._todos("SELECT * FROM eventos WHERE sessao_id IS ? AND investigacao_id=? ORDER BY seq",
                               (sessao_id, investigacao_id))
        return self._todos("SELECT * FROM eventos WHERE sessao_id IS ? ORDER BY seq", (sessao_id,))

    def registrar_mensagem(self, sessao_id: str, papel: str, conteudo: str, *, meta: Optional[dict] = None,
                           investigacao_id: Optional[str] = None, acao_id: Optional[str] = None) -> dict[str, Any]:
        msg = {"id": novo_id("m"), "sessao_id": sessao_id, "investigacao_id": investigacao_id, "acao_id": acao_id,
               "ts": agora(), "papel": papel, "conteudo": conteudo, "meta": meta or {}}
        self._inserir("mensagens", msg)
        self._anexar_jsonl(self.dir_sessao(sessao_id) / "chat.jsonl", msg)
        return msg

    def mensagens(self, sessao_id: str, desde_seq: int = 0) -> list[dict[str, Any]]:
        linhas = self._todos("SELECT * FROM mensagens WHERE sessao_id=? AND seq>? ORDER BY seq", (sessao_id, desde_seq))
        return linhas

    def ultima_seq_mensagem(self, sessao_id: str) -> int:
        r = self._um("SELECT MAX(seq) AS s FROM mensagens WHERE sessao_id=?", (sessao_id,))
        return int((r or {}).get("s") or 0)

    def registrar_consulta(self, sessao_id: str, *, modelo_id: Optional[str], modelo_digest: Optional[str],
                           mensagens: list[dict], resposta: Optional[str], duracao_ms: int,
                           erro: Optional[str]) -> dict[str, Any]:
        c = {"id": novo_id("q"), "sessao_id": sessao_id, "ts": agora(), "modelo_id": modelo_id,
             "modelo_digest": modelo_digest, "mensagens": mensagens, "resposta": resposta, "duracao_ms": duracao_ms,
             "erro": erro}
        self._inserir("consultas", c)
        self._anexar_jsonl(self.dir_sessao(sessao_id) / "consultas-modelo.jsonl", c)
        return c

    def consultas(self, sessao_id: str) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM consultas WHERE sessao_id=? ORDER BY ts", (sessao_id,))

    # ---------------- sugestões do modelo sobre o plano ---------------- #
    def criar_sugestao(self, sessao_id: str, texto: str, item: Optional[str]) -> dict[str, Any]:
        s = {"id": novo_id("g"), "sessao_id": sessao_id, "ts": agora(), "item": item, "texto": texto, "estado": "pendente"}
        self._inserir("sugestoes", s)
        return self.sugestao(s["id"])  # type: ignore[return-value]

    def sugestao(self, gid: str) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM sugestoes WHERE id=?", (gid,))

    def sugestoes(self, sessao_id: str) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM sugestoes WHERE sessao_id=? ORDER BY ts", (sessao_id,))

    def atualizar_sugestao(self, gid: str, **campos: Any) -> None:
        self._atualizar("sugestoes", "id", gid, campos)

    # ---------------- resultados brutos (imutáveis) ---------------- #
    def salvar_resultado(self, sessao_id: str, acao_id: str, nome: str, dados: bytes) -> dict[str, Any]:
        if not NOME_SEGURO_RE.match(nome) or not re.match(r"^a-[0-9a-f]{10}$", acao_id):
            raise ValueError("nome de arquivo inseguro")
        rel = f"resultados-ferramentas/{acao_id}.{nome}"
        caminho = self.dir_sessao(sessao_id) / rel
        fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
        os.chmod(caminho, 0o444)
        r = {"id": novo_id("r"), "sessao_id": sessao_id, "acao_id": acao_id, "nome": nome, "arquivo": rel,
             "tamanho": len(dados), "sha256": sha256_bytes(dados), "criado_em": agora()}
        self._inserir("resultados", r)
        return r

    def resultado(self, rid: str) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM resultados WHERE id=?", (rid,))

    def resultados(self, sessao_id: str, acao_id: Optional[str] = None) -> list[dict[str, Any]]:
        if acao_id:
            return self._todos("SELECT * FROM resultados WHERE sessao_id=? AND acao_id=? ORDER BY criado_em",
                               (sessao_id, acao_id))
        return self._todos("SELECT * FROM resultados WHERE sessao_id=? ORDER BY criado_em", (sessao_id,))

    def ler_resultado(self, rid: str) -> tuple[dict[str, Any], bytes]:
        r = self.resultado(rid)
        if r is None:
            raise KeyError(rid)
        caminho = (self.dir_sessao(r["sessao_id"]) / r["arquivo"])
        if caminho.is_symlink():
            raise ValueError("link simbólico recusado")
        return r, caminho.read_bytes()

    # ---------------- evidências ---------------- #
    def criar_evidencia(self, sessao_id: str, *, investigacao_id: Optional[str], resultado_id: Optional[str],
                        acao_id: Optional[str], nota: str, operador: Optional[str]) -> dict[str, Any]:
        r = self._um("SELECT COUNT(*) AS n FROM evidencias WHERE sessao_id=?", (sessao_id,))
        eid = f"EV-{int(r['n']) + 1:03d}"  # type: ignore[index]
        e = {"id": eid, "sessao_id": sessao_id, "investigacao_id": investigacao_id, "resultado_id": resultado_id,
             "acao_id": acao_id, "nota": nota, "operador": operador, "criado_em": agora()}
        self._inserir("evidencias", e)
        res = self.resultado(resultado_id) if resultado_id else None
        arq = self.dir_sessao(sessao_id) / "evidencias" / f"{eid}.json"
        with open(arq, "x", encoding="utf-8") as f:
            json.dump({**e, "resultado": res}, f, ensure_ascii=False, indent=2)
        return e

    def evidencias(self, sessao_id: str) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM evidencias WHERE sessao_id=? ORDER BY id", (sessao_id,))

    # ---------------- habilitações e catálogo ---------------- #
    def habilitacao(self, ferramenta_id: str) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM habilitacoes WHERE ferramenta_id=? AND ativo=1", (ferramenta_id,))

    def salvar_habilitacao(self, ferramenta_id: str, *, manifesto_sha256: str, executavel_sha256: str,
                           doc_sha256: Optional[str], operador: Optional[str], justificativa: Optional[str]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO habilitacoes(ferramenta_id,manifesto_sha256,executavel_sha256,doc_sha256,operador,justificativa,habilitado_em,ativo) "
                "VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(ferramenta_id) DO UPDATE SET manifesto_sha256=excluded.manifesto_sha256,"
                "executavel_sha256=excluded.executavel_sha256,doc_sha256=excluded.doc_sha256,operador=excluded.operador,"
                "justificativa=excluded.justificativa,habilitado_em=excluded.habilitado_em,ativo=1",
                (ferramenta_id, manifesto_sha256, executavel_sha256, doc_sha256, operador, justificativa, agora()))
            self._conn.commit()

    def desabilitar(self, ferramenta_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE habilitacoes SET ativo=0 WHERE ferramenta_id=?", (ferramenta_id,))
            self._conn.commit()

    def catalogo(self, tipo: str, incluir_removidos: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM catalogo WHERE tipo=?" + ("" if incluir_removidos else " AND removido_em IS NULL")
        return self._todos(sql + " ORDER BY rid", (tipo,))

    def substituir_catalogo(self, tipo: str, itens: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        """Atualiza o catálogo e devolve {novos, alterados, removidos}."""
        antigos = {r["rid"]: r for r in self.catalogo(tipo, incluir_removidos=True)}
        t = agora()
        diff = {"novos": [], "alterados": [], "removidos": []}
        with self._lock:
            for rid, d in itens.items():
                h = d.get("hash")
                ant = antigos.get(rid)
                if ant is None or ant["removido_em"]:
                    diff["novos"].append(rid)
                elif ant["hash"] != h:
                    diff["alterados"].append(rid)
                self._conn.execute(
                    "INSERT INTO catalogo(tipo,rid,hash,estado,dados_json,visto_em,removido_em) VALUES(?,?,?,?,?,?,NULL) "
                    "ON CONFLICT(tipo,rid) DO UPDATE SET hash=excluded.hash,estado=excluded.estado,"
                    "dados_json=excluded.dados_json,visto_em=excluded.visto_em,removido_em=NULL",
                    (tipo, rid, h, d.get("estado"), json.dumps(d, ensure_ascii=False), t))
            for rid, ant in antigos.items():
                if rid not in itens and not ant["removido_em"]:
                    diff["removidos"].append(rid)
                    self._conn.execute("UPDATE catalogo SET removido_em=? WHERE tipo=? AND rid=?", (t, tipo, rid))
            self._conn.commit()
        return diff

    def salvar_varredura(self, vid: str, iniciada_em: str, concluida_em: Optional[str], estado: str,
                         dados: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO varreduras(id,iniciada_em,concluida_em,estado,dados_json) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET concluida_em=excluded.concluida_em,estado=excluded.estado,dados_json=excluded.dados_json",
                (vid, iniciada_em, concluida_em, estado, json.dumps(dados, ensure_ascii=False)))
            self._conn.commit()

    def ultima_varredura(self) -> Optional[dict[str, Any]]:
        return self._um("SELECT * FROM varreduras ORDER BY iniciada_em DESC LIMIT 1")

    # ---------------- exportação ---------------- #
    _REDIGIR_ARQUIVOS = ("chat.jsonl", "eventos.jsonl", "consultas-modelo.jsonl", "relatorio.md")

    def _arquivos_sessao(self, sessao_id: str, prefixos: tuple[str, ...]) -> list[tuple[str, Path]]:
        base = self.dir_sessao(sessao_id)
        achados: list[tuple[str, Path]] = []
        if not base.exists():
            return achados
        for caminho in sorted(base.rglob("*")):
            if caminho.is_symlink() or not caminho.is_file():
                continue
            rel = caminho.relative_to(base).as_posix()
            real = caminho.resolve()
            if base.resolve() not in real.parents:
                continue
            if any(rel == p or rel.startswith(p) for p in prefixos):
                achados.append((rel, caminho))
        return achados

    def exportar_zip(self, sessao_id: str, prefixos: tuple[str, ...]) -> bytes:
        """ZIP apenas com arquivos desta sessão, com MANIFESTO-HASHES.json (SHA-256)."""
        manifesto: list[dict[str, Any]] = []
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for rel, caminho in self._arquivos_sessao(sessao_id, prefixos):
                original = caminho.read_bytes()
                dados = original
                redigido = rel in self._REDIGIR_ARQUIVOS or rel.startswith("resultados-ferramentas/") \
                    or rel.startswith("evidencias/")
                if redigido:
                    dados = redigir_texto(original.decode("utf-8", errors="replace")).encode("utf-8")
                z.writestr(rel, dados)
                manifesto.append({"arquivo": rel, "tamanho": len(dados), "sha256": sha256_bytes(dados),
                                  "credenciais_ocultadas": bool(redigido and dados != original),
                                  "sha256_original": sha256_bytes(original) if redigido else None})
            z.writestr("MANIFESTO-HASHES.json", json.dumps(
                {"sessao_id": sessao_id, "gerado_em": agora(), "arquivos": manifesto}, ensure_ascii=False, indent=2))
        return buf.getvalue()

    def exportar_texto(self, sessao_id: str, nome: str) -> bytes:
        caminho = self.dir_sessao(sessao_id) / nome
        if nome not in ("chat.jsonl", "eventos.jsonl", "relatorio.md", "consultas-modelo.jsonl") or caminho.is_symlink():
            raise ValueError("arquivo não exportável")
        if not caminho.exists():
            return b""
        return redigir_texto(caminho.read_text(encoding="utf-8", errors="replace")).encode("utf-8")
