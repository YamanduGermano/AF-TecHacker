"""Descoberta, validação e catálogo de modelos e ferramentas.

A varredura **apenas descobre e valida**. Ela nunca executa binários, não habilita nada e não baixa
modelos. Executar, importar, habilitar e alterar uma sessão são operações separadas e explícitas.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import ValidationError

from proxy.params import PolicyError
from proxy.policy import ESQUEMA_PERFIL, PERFIS_RECONHECIDOS, PERFIS_SCAN_ADAPTADOR
from proxy.schemas import Manifesto

from .config import Config
from .ollama import NOME_MODELO_RE, ClienteOllama, ErroOllama, ler_modelfile
from .storage import Armazenamento, agora, novo_id

CHAVES_MANIFESTO_PROIBIDAS = {
    "shell", "comando", "command", "cmd", "args", "argumentos", "argv", "flags", "flags_livres", "destino", "host",
    "url_destino", "allow_shell", "permitir_shell", "script", "proxy", "env", "privileged", "network", "rede",
}
DOC_MAX_BYTES = 200_000
EXT_MODELO = {".gguf", ".safetensors", ".bin"}


def _sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


_CACHE_HASH: dict[tuple[str, int, int], str] = {}


def _sha_arquivo(p: Path, usar_cache: bool = True) -> str:
    st = p.stat()
    chave = (str(p), st.st_mtime_ns, st.st_size)
    if usar_cache and chave in _CACHE_HASH:
        return _CACHE_HASH[chave]
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    if usar_cache:
        _CACHE_HASH[chave] = h.hexdigest()
    return h.hexdigest()


def _chaves_proibidas(obj: Any, prefixo: str = "") -> list[str]:
    achadas: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in CHAVES_MANIFESTO_PROIBIDAS:
                achadas.append(f"{prefixo}{k}")
            if k not in ("esquema_entrada", "esquema_saida"):
                achadas += _chaves_proibidas(v, f"{prefixo}{k}.")
    return achadas


class Descoberta:
    def __init__(self, cfg: Config, arm: Armazenamento, ollama: ClienteOllama):
        self.cfg, self.arm, self.ollama = cfg, arm, ollama
        self._varreduras: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._exec_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Ferramentas
    # ------------------------------------------------------------------ #
    def _analisar_ferramenta(self, pasta: Path, origem: str, usar_cache: bool = True) -> dict[str, Any]:
        id_pasta = pasta.name
        item: dict[str, Any] = {
            "id": id_pasta, "origem": origem, "erros": [], "avisos": [], "manifesto": None, "perfil": None,
            "descricao": None, "manifesto_sha256": None, "executavel_sha256": None, "doc_sha256": None,
            "documentacao": None, "executavel": None, "limites": None, "politica_escopo": None, "detectada": True,
        }
        erros, avisos = item["erros"], item["avisos"]
        mpath = pasta / "manifest.json"
        if not mpath.is_file():
            erros.append("manifest.json ausente")
            return self._fechar(item)
        try:
            bruto = mpath.read_bytes()
            dados = json.loads(bruto.decode("utf-8"))
        except (OSError, ValueError) as e:
            erros.append(f"manifesto ilegível ou JSON inválido: {e}")
            return self._fechar(item)
        item["manifesto_sha256"] = _sha(bruto)
        proibidas = _chaves_proibidas(dados)
        if proibidas:
            erros.append("o manifesto não pode pedir shell livre, destino alternativo, flags livres ou permissões "
                         f"fora da política global (chaves: {', '.join(proibidas)})")
        try:
            m = Manifesto.model_validate(dados)
        except ValidationError as e:
            for x in e.errors():
                erros.append(f"manifesto: {'.'.join(str(p) for p in x['loc'])}: {x['msg']}")
            return self._fechar(item)
        item["manifesto"] = m.model_dump(mode="json")
        item.update(perfil=m.perfil, descricao=m.descricao_modelo, limites=item["manifesto"]["limites"],
                    politica_escopo=item["manifesto"]["politica_escopo"], executavel=m.executavel)
        if m.id != id_pasta:
            erros.append(f"id do manifesto ({m.id!r}) difere do nome da pasta ({id_pasta!r})")
        if m.perfil not in PERFIS_RECONHECIDOS:
            erros.append(f"perfil {m.perfil!r} não reconhecido: indisponível até existir um adaptador específico revisado "
                         f"(reconhecidos: {', '.join(sorted(PERFIS_RECONHECIDOS))})")
        pol, g = m.politica_escopo, self.cfg.politica
        fora = sorted({x.upper() for x in pol.metodos} - g.metodos_permitidos)
        if fora:
            erros.append(f"métodos {fora} fora da política global ({sorted(g.metodos_permitidos)})")
        fora_cab = sorted({x.lower() for x in pol.cabecalhos_permitidos} - {x.lower() for x in g.cabecalhos_permitidos})
        if fora_cab:
            erros.append(f"cabeçalhos {fora_cab} fora da política global")
        if pol.permitir_corpo and not g.permitir_corpo:
            erros.append("permitir_corpo=true é incompatível com a política global (PERMITIR_CORPO_REQUISICAO=false)")
        if m.perfil == "port_scanner_nmap":
            invalidos = sorted(set(pol.perfis_varredura) - PERFIS_SCAN_ADAPTADOR)
            if invalidos:
                erros.append(f"perfis de varredura desconhecidos: {invalidos}")
        if m.limites.timeout_s > g.max_timeout_s:
            erros.append(f"timeout_s ({m.limites.timeout_s}) excede o máximo global ({g.max_timeout_s})")
        if m.limites.max_saida_bytes > g.max_saida_bytes:
            erros.append(f"max_saida_bytes excede o máximo global ({g.max_saida_bytes})")

        # Executável: existência, permissão, hash. Nunca é executado na varredura.
        exe = (pasta / m.executavel).resolve()
        if pasta.resolve() not in exe.parents:
            erros.append("executável fora da pasta da ferramenta (link simbólico ou caminho inválido)")
        elif not exe.is_file():
            erros.append(f"executável {m.executavel!r} não encontrado")
        else:
            if not os.access(exe, os.X_OK):
                erros.append("executável sem permissão de execução (chmod +x)")
            item["executavel_sha256"] = _sha_arquivo(exe, usar_cache)

        # Documentação associada.
        doc_rel = m.documentacao or f"{m.id}.md"
        item["documentacao"] = doc_rel
        dpath = (self.cfg.documentacoes_dir / doc_rel).resolve()
        base_docs = self.cfg.documentacoes_dir.resolve()
        if base_docs not in dpath.parents or not dpath.is_file():
            avisos.append(f"SEM DOCUMENTAÇÃO: dados/documentacoes/{doc_rel} não encontrado; a ferramenta não poderá ser usada")
        else:
            bruto_doc = dpath.read_bytes()
            if len(bruto_doc) > DOC_MAX_BYTES:
                erros.append("documentação grande demais")
            elif not bruto_doc.decode("utf-8", errors="replace").strip():
                avisos.append(f"SEM DOCUMENTAÇÃO: dados/documentacoes/{doc_rel} está vazio")
            else:
                item["doc_sha256"] = _sha(bruto_doc)
        return self._fechar(item)

    @staticmethod
    def _fechar(item: dict[str, Any]) -> dict[str, Any]:
        item["hash"] = _sha("|".join(str(item.get(k)) for k in ("manifesto_sha256", "executavel_sha256", "doc_sha256")).encode())
        return item

    def _derivar_status(self, item: dict[str, Any]) -> dict[str, Any]:
        """Status exibido: detectada | invalida | sem_documentacao | pendente_habilitacao | habilitada | suspensa_alterada."""
        item = dict(item)
        if item.get("origem") == "__shared__":
            item["status"] = "detectada"
            item["avisos"] = [*item["avisos"], "Candidata em __shared__: mova para dados/ferramentas/<id>/ para poder habilitar. "
                              "Nada nesta pasta é executado automaticamente."]
            item["utilizavel"] = False
            return item
        hab = self.arm.habilitacao(item["id"])
        item["habilitacao"] = hab
        if item["erros"]:
            item["status"] = "invalida"
        elif not item.get("doc_sha256"):
            item["status"] = "sem_documentacao"
        elif hab is None:
            item["status"] = "pendente_habilitacao"
        elif (hab["manifesto_sha256"], hab["executavel_sha256"], hab["doc_sha256"]) == (
                item["manifesto_sha256"], item["executavel_sha256"], item["doc_sha256"]):
            item["status"] = "habilitada"
        else:
            item["status"] = "suspensa_alterada"
            item["avisos"] = [*item["avisos"], "Manifesto, documentação ou executável mudou depois da revisão: "
                              "execução suspensa até nova revisão e habilitação."]
        item["utilizavel"] = item["status"] == "habilitada"
        return item

    def _escanear_ferramentas(self, usar_cache: bool = True) -> dict[str, dict[str, Any]]:
        achadas: dict[str, dict[str, Any]] = {}
        for origem, base in (("ferramentas", self.cfg.ferramentas_dir), ("__shared__", self.cfg.shared_dir)):
            if not base.is_dir():
                continue
            for pasta in sorted(base.iterdir()):
                if pasta.name.startswith(".") or not pasta.is_dir() or pasta.is_symlink():
                    continue
                if origem == "__shared__" and not (pasta / "manifest.json").is_file():
                    continue
                item = self._analisar_ferramenta(pasta, origem, usar_cache)
                chave = item["id"] if origem == "ferramentas" else f"__shared__/{item['id']}"
                achadas[chave] = item
        return achadas

    def ferramentas(self, usar_cache: bool = True) -> list[dict[str, Any]]:
        """Catálogo atual (estado real do volume + habilitações)."""
        atuais = self._escanear_ferramentas(usar_cache)
        return [self._derivar_status(v) for v in atuais.values()]

    def ferramenta(self, tool_id: str, usar_cache: bool = True) -> Optional[dict[str, Any]]:
        for f in self.ferramentas(usar_cache):
            if f["id"] == tool_id and f["origem"] == "ferramentas":
                return f
        return None

    def habilitar(self, tool_id: str, *, manifesto_sha256: str, operador: Optional[str],
                  justificativa: Optional[str]) -> dict[str, Any]:
        f = self.ferramenta(tool_id, usar_cache=False)
        if f is None:
            raise PolicyError("ferramenta_inexistente", f"ferramenta {tool_id!r} não encontrada")
        if f["status"] in ("invalida", "sem_documentacao"):
            raise PolicyError("nao_habilitavel", f"ferramenta {f['status']}: " + "; ".join(f["erros"] + f["avisos"]))
        if f["manifesto_sha256"] != manifesto_sha256:
            raise PolicyError("revisao_desatualizada",
                              "o manifesto mudou depois da sua revisão (hash diferente); revise novamente")
        self.arm.salvar_habilitacao(tool_id, manifesto_sha256=f["manifesto_sha256"], executavel_sha256=f["executavel_sha256"],
                                    doc_sha256=f["doc_sha256"], operador=operador, justificativa=justificativa)
        self.arm.registrar_evento(None, "ferramenta_habilitada", {
            "ferramenta_id": tool_id, "operador": operador, "justificativa": justificativa,
            "manifesto_sha256": f["manifesto_sha256"], "executavel_sha256": f["executavel_sha256"],
            "doc_sha256": f["doc_sha256"], "politica": f["politica_escopo"], "limites": f["limites"]})
        return self.ferramenta(tool_id)  # type: ignore[return-value]

    def desabilitar(self, tool_id: str, operador: Optional[str]) -> None:
        self.arm.desabilitar(tool_id)
        self.arm.registrar_evento(None, "ferramenta_desabilitada", {"ferramenta_id": tool_id, "operador": operador})

    def ferramentas_habilitadas(self) -> list[dict[str, Any]]:
        return [f for f in self.ferramentas() if f["utilizavel"]]

    def revalidar_ferramenta(self, tool_id: str, hashes_esperados: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Revalida a identidade imediatamente antes do uso; levanta PolicyError se mudou."""
        f = self.ferramenta(tool_id, usar_cache=False)  # identidade recalculada do disco, sem cache
        if f is None or f["status"] == "invalida":
            raise PolicyError("ferramenta_indisponivel", f"ferramenta {tool_id!r} indisponível ou inválida")
        if f["status"] == "suspensa_alterada":
            raise PolicyError("ferramenta_alterada", "manifesto/documentação/executável mudou desde a revisão; "
                                                     "nova revisão e habilitação necessárias")
        if f["status"] != "habilitada":
            raise PolicyError("ferramenta_indisponivel", f"ferramenta {tool_id!r} não está habilitada ({f['status']})")
        if hashes_esperados:
            for k in ("manifesto_sha256", "executavel_sha256", "doc_sha256"):
                if hashes_esperados.get(k) and hashes_esperados[k] != f[k]:
                    raise PolicyError("ferramenta_alterada", f"{k} diferente do registrado quando a ação foi proposta")
        return f

    # ------------------------------------------------------------------ #
    # Modelos
    # ------------------------------------------------------------------ #
    def _escanear_modelos(self, erros: list[str]) -> dict[str, dict[str, Any]]:
        achados: dict[str, dict[str, Any]] = {}
        try:
            registrados = self.ollama.tags()
        except ErroOllama as e:
            erros.append(f"Ollama: {e}")
            registrados = []
        for m in registrados:
            nome = m.get("name") or m.get("model")
            if not nome:
                continue
            digest = m.get("digest", "")
            item = {"id": nome, "tipo": "registrado", "digest": digest, "versao": digest[:12] or None,
                    "tamanho": m.get("size"), "modificado_em": m.get("modified_at"), "estado": "disponivel", "erro": None,
                    "hash": digest or nome}
            try:
                self.ollama.show(nome)  # validado pela API local
            except ErroOllama as e:
                item.update(estado="erro", erro=str(e))
                erros.append(f"modelo {nome}: {e}")
            achados[f"registrado:{nome}"] = item
        if self.cfg.importar_dir.is_dir():
            for arq in sorted(self.cfg.importar_dir.iterdir()):
                if arq.name.startswith(".") or not arq.is_file() or arq.is_symlink():
                    continue
                if arq.suffix.lower() not in EXT_MODELO:
                    continue
                st = arq.stat()
                item = {"id": arq.name, "tipo": "candidato", "tamanho": st.st_size, "digest": None, "versao": None,
                        "modificado_em": st.st_mtime, "estado": "pendente_importacao", "erro": None,
                        "hash": f"{st.st_size}:{st.st_mtime_ns}"}
                erro = self._validar_candidato(arq)
                if erro:
                    item.update(estado="invalido", erro=erro)
                achados[f"candidato:{arq.name}"] = item
        return achados

    def _validar_candidato(self, arq: Path) -> Optional[str]:
        if arq.suffix.lower() != ".gguf":
            return "formato não suportado para importação (somente GGUF acompanhado de Modelfile)"
        try:
            with open(arq, "rb") as f:
                if f.read(4) != b"GGUF":
                    return "arquivo não tem a assinatura GGUF"
        except OSError as e:
            return f"ilegível: {e}"
        modelfile = self._achar_modelfile(arq)
        if modelfile is None:
            return f"definição de importação ausente (esperado {arq.stem}.Modelfile ou Modelfile na mesma pasta)"
        try:
            d = ler_modelfile(modelfile.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            return f"Modelfile ilegível: {e}"
        origem = (d.get("from") or "").strip()
        if not origem:
            return "Modelfile sem linha FROM"
        if origem.replace("\\", "/").lstrip("./") != arq.name:
            return f"FROM deve referenciar apenas {arq.name!r} (relativo, mesma pasta); encontrado {origem!r}"
        return None

    def _achar_modelfile(self, arq: Path) -> Optional[Path]:
        for nome in (f"{arq.stem}.Modelfile", f"{arq.stem}.modelfile", "Modelfile"):
            p = arq.parent / nome
            if p.is_file() and not p.is_symlink():
                return p
        return None

    def modelos(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self._escanear_modelos([]).values()]

    def modelo_disponivel(self, modelo_id: str) -> Optional[dict[str, Any]]:
        for m in self.modelos():
            if m["tipo"] == "registrado" and m["id"] == modelo_id and m["estado"] == "disponivel":
                return m
        return None

    def importar_modelo(self, arquivo: str, nome: str, operador: Optional[str]) -> dict[str, Any]:
        """Importação explícita (ação do usuário) de um candidato GGUF validado."""
        if not NOME_MODELO_RE.match(nome):
            raise PolicyError("nome_invalido", "nome do modelo deve casar com ^[a-z0-9][a-z0-9._:/-]{1,63}$")
        if "/" in arquivo or "\\" in arquivo or arquivo.startswith("."):
            raise PolicyError("arquivo_invalido", "informe apenas o nome do arquivo em modelos/importar")
        arq = (self.cfg.importar_dir / arquivo)
        if not arq.is_file() or arq.is_symlink():
            raise PolicyError("arquivo_inexistente", f"{arquivo} não encontrado em modelos/importar")
        erro = self._validar_candidato(arq)
        if erro:
            raise PolicyError("candidato_invalido", erro)
        mf = ler_modelfile(self._achar_modelfile(arq).read_text(encoding="utf-8"))  # type: ignore[union-attr]
        try:
            self.ollama.importar_gguf(arq, nome, mf)
        except ErroOllama as e:
            self.arm.registrar_evento(None, "importacao_modelo_falhou", {"arquivo": arquivo, "nome": nome,
                                                                          "operador": operador, "erro": str(e)})
            raise PolicyError("importacao_falhou", str(e)) from e
        self.arm.registrar_evento(None, "modelo_importado", {"arquivo": arquivo, "nome": nome, "operador": operador})
        return {"ok": True, "modelo": nome}

    # ------------------------------------------------------------------ #
    # Varredura (início do backend e sob demanda)
    # ------------------------------------------------------------------ #
    def varrer(self, varredura: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        with self._exec_lock:
            v = varredura if varredura is not None else self._nova_varredura()
            erros: list[str] = v["erros"]

            def etapa(nome: str, estado: str, itens: int = 0, pct: int = 0):
                for e in v["etapas"]:
                    if e["nome"] == nome:
                        e.update(estado=estado, itens=itens)
                        break
                v["progresso"] = pct

            etapa("modelos", "em_andamento", pct=10)
            modelos = self._escanear_modelos(erros)
            d_mod = self.arm.substituir_catalogo("modelo", {k: dict(x) for k, x in modelos.items()})
            etapa("modelos", "concluida", len(modelos), 50)

            etapa("ferramentas", "em_andamento", pct=55)
            ferr = self._escanear_ferramentas(usar_cache=False)
            avisos = v["avisos"]
            for k, item in ferr.items():
                for er in item["erros"]:
                    erros.append(f"ferramenta {k}: {er}")
                for av in item["avisos"]:
                    avisos.append(f"ferramenta {k}: {av}")
            for k, x in ferr.items():
                x["estado"] = self._derivar_status(x)["status"]
            d_fer = self.arm.substituir_catalogo("ferramenta", {k: dict(x) for k, x in ferr.items()})
            etapa("ferramentas", "concluida", len(ferr), 95)

            v["novos"] = {"modelos": d_mod["novos"], "ferramentas": d_fer["novos"]}
            v["alterados"] = {"modelos": d_mod["alterados"], "ferramentas": d_fer["alterados"]}
            v["removidos"] = {"modelos": d_mod["removidos"], "ferramentas": d_fer["removidos"]}
            v["concluida_em"] = agora()
            v["progresso"] = 100
            v["estado"] = "concluida_com_erros" if erros else "concluida"
            self.arm.salvar_varredura(v["id"], v["iniciada_em"], v["concluida_em"], v["estado"], v)
            if any(v[k]["modelos"] or v[k]["ferramentas"] for k in ("novos", "alterados", "removidos")):
                self.arm.registrar_evento(None, "varredura_com_mudancas", {
                    "varredura_id": v["id"], "novos": v["novos"], "alterados": v["alterados"], "removidos": v["removidos"]})
            return v

    def _nova_varredura(self) -> dict[str, Any]:
        v = {"id": novo_id("v"), "iniciada_em": agora(), "concluida_em": None, "estado": "em_andamento", "progresso": 0,
             "etapas": [{"nome": "modelos", "estado": "pendente", "itens": 0},
                        {"nome": "ferramentas", "estado": "pendente", "itens": 0}],
             "novos": {"modelos": [], "ferramentas": []}, "alterados": {"modelos": [], "ferramentas": []},
             "removidos": {"modelos": [], "ferramentas": []}, "erros": [], "avisos": []}
        with self._lock:
            self._varreduras[v["id"]] = v
        return v

    def iniciar_varredura(self, sincrona: bool = False) -> dict[str, Any]:
        v = self._nova_varredura()
        if sincrona:
            return self.varrer(v)

        def alvo():
            try:
                self.varrer(v)
            except Exception as e:  # noqa: BLE001
                v["erros"].append(f"falha inesperada: {e}")
                v["estado"] = "falhou"
                v["concluida_em"] = agora()
                self.arm.salvar_varredura(v["id"], v["iniciada_em"], v["concluida_em"], v["estado"], v)

        threading.Thread(target=alvo, daemon=True).start()
        return v

    def varredura(self, vid: str) -> Optional[dict[str, Any]]:
        with self._lock:
            if vid in self._varreduras:
                return self._varreduras[vid]
        return None

    def ultima_varredura(self) -> Optional[dict[str, Any]]:
        with self._lock:
            if self._varreduras:
                return list(self._varreduras.values())[-1]
        r = self.arm.ultima_varredura()
        return r["dados"] if r else None
