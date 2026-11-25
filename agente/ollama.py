"""Cliente mínimo do Ollama (API local interna; nunca baixa modelos da internet)."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterator, Optional

import httpx


class ErroOllama(Exception):
    pass


def ler_modelfile(texto: str) -> dict[str, Any]:
    """Interpreta o subconjunto de Modelfile usado na importação: FROM, TEMPLATE, SYSTEM, PARAMETER."""
    saida: dict[str, Any] = {"from": None, "template": None, "system": None, "parameters": {}}
    i, linhas = 0, texto.splitlines()
    while i < len(linhas):
        l = linhas[i].strip()
        i += 1
        if not l or l.startswith("#"):
            continue
        chave, _, resto = l.partition(" ")
        chave = chave.upper()
        resto = resto.strip()
        if chave in ("TEMPLATE", "SYSTEM") and resto.startswith('"""'):
            corpo = resto[3:]
            if corpo.endswith('"""') and len(corpo) >= 3:
                valor = corpo[:-3]
            else:
                partes = [corpo]
                while i < len(linhas):
                    ln = linhas[i]
                    i += 1
                    if ln.rstrip().endswith('"""'):
                        partes.append(ln.rstrip()[:-3])
                        break
                    partes.append(ln)
                valor = "\n".join(partes)
            saida[chave.lower()] = valor
        elif chave in ("TEMPLATE", "SYSTEM"):
            saida[chave.lower()] = resto.strip('"')
        elif chave == "FROM":
            saida["from"] = resto
        elif chave == "PARAMETER":
            k, _, v = resto.partition(" ")
            if k:
                try:
                    saida["parameters"][k] = float(v) if "." in v else int(v)
                except ValueError:
                    saida["parameters"][k] = v.strip('"')
    return saida


class ClienteOllama:
    def __init__(self, base_url: str, client: Optional[httpx.Client] = None, timeout_s: float = 600.0,
                 temperatura: float = 0.2):
        self.base_url = base_url.rstrip("/")
        self.temperatura = temperatura
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0))

    def _req(self, metodo: str, caminho: str, **kw: Any) -> Any:
        try:
            r = self._client.request(metodo, f"{self.base_url}{caminho}", **kw)
        except httpx.HTTPError as e:
            raise ErroOllama(f"Ollama inacessível: {e}") from e
        if r.status_code >= 400:
            raise ErroOllama(f"Ollama respondeu {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    def saude(self) -> bool:
        try:
            self._req("GET", "/api/tags")
            return True
        except ErroOllama:
            return False

    def tags(self) -> list[dict[str, Any]]:
        return list(self._req("GET", "/api/tags").get("models", []))

    def show(self, nome: str) -> dict[str, Any]:
        return self._req("POST", "/api/show", json={"model": nome})

    def chat(self, modelo: str, mensagens: list[dict[str, str]]) -> str:
        dados = self._req("POST", "/api/chat", json={
            "model": modelo, "messages": mensagens, "stream": False, "format": "json",
            "options": {"temperature": self.temperatura},
        })
        conteudo = (dados.get("message") or {}).get("content")
        if not isinstance(conteudo, str):
            raise ErroOllama("resposta do Ollama sem conteúdo")
        return conteudo

    # --- importação explícita de GGUF --- #
    @staticmethod
    def _blocos(caminho: Path) -> Iterator[bytes]:
        with open(caminho, "rb") as f:
            for b in iter(lambda: f.read(8 << 20), b""):
                yield b

    @staticmethod
    def sha256_arquivo(caminho: Path) -> str:
        h = hashlib.sha256()
        for b in ClienteOllama._blocos(caminho):
            h.update(b)
        return h.hexdigest()

    def importar_gguf(self, caminho: Path, nome: str, modelfile: dict[str, Any]) -> None:
        digest = self.sha256_arquivo(caminho)
        try:
            r = self._client.post(f"{self.base_url}/api/blobs/sha256:{digest}", content=self._blocos(caminho))
        except httpx.HTTPError as e:
            raise ErroOllama(f"falha ao enviar blob: {e}") from e
        if r.status_code >= 400:
            raise ErroOllama(f"envio do blob falhou ({r.status_code}): {r.text[:300]}")
        corpo: dict[str, Any] = {"model": nome, "files": {caminho.name: f"sha256:{digest}"}, "stream": False}
        for k in ("template", "system"):
            if modelfile.get(k):
                corpo[k] = modelfile[k]
        if modelfile.get("parameters"):
            corpo["parameters"] = modelfile["parameters"]
        self._req("POST", "/api/create", json=corpo)


NOME_MODELO_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{1,63}$")
