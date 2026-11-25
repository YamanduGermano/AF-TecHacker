import copy
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import threading
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.parse import urlsplit

from .executor import run
from .storage import now, digest


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def text(value, limit=12000, field="Texto"):
    if not isinstance(value, str):
        raise ValueError(f"{field}: esperado texto; recebido {type(value).__name__}.")
    if "\x00" in value:
        raise ValueError(f"{field}: contém um caractere nulo, que não é permitido.")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{field}: {len(value)} caracteres; limite de {limit}.")
    return value


def executable(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.+-]{0,79}", name):
        raise ValueError("Use apenas o nome do comando, sem caminho ou argumentos.")
    path = shutil.which(name)
    if not path:
        return None
    path = str(Path(path).resolve())
    stat = Path(path).stat()
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    sha = hasher.hexdigest()
    return {"path": path, "sha256": sha, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


class Resources:
    def __init__(self, store, ollama_url="http://127.0.0.1:11434"):
        self.store = store
        parsed = urlsplit(ollama_url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("Ollama deve usar HTTP em loopback, sem caminho ou credenciais.")
        self.url = ollama_url.rstrip("/")
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.path = store.root / "catalogo.json"
        self.catalog = json.loads(self.path.read_text()) if self.path.exists() else []
        self.models = []
        self.checked_at = None
        self.error = None
        self.save()

    def save(self):
        self.store.write(self.path, self.catalog)

    def request(self, route, payload=None, timeout=5):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.url + route, data=data, headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Resposta do Ollama excedeu o limite.")
        return json.loads(raw)

    def refresh(self):
        try:
            response = self.request("/api/tags")
            models = [{"name": m["name"], "digest": m.get("digest"), "size": m.get("size"), "details": m.get("details", {})}
                      for m in response.get("models", [])]
            error = None
        except Exception as exc:
            models, error = [], "Ollama indisponível. Verifique se ele está iniciado na máquina. " + str(exc)[:250]
        with self.store.lock:
            self.models, self.error = models, error
            for tool in self.catalog:
                tool["resolved"] = executable(tool["name"])
                tool["checked_at"] = now()
            self.checked_at = now()
            self.save()
            return self.snapshot()

    def stream_chat(self, payload, job, on_content, timeout=180):
        """NDJSON streaming; closing the socket interrupts blocked reads immediately."""
        parsed = urlsplit(self.url)
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
        pieces = []
        complete = False
        deadline_hit = threading.Event()
        timer = None
        response = None
        try:
            if job.cancel.is_set():
                return {"message": {"content": ""}}
            connection.connect()
            sock = connection.sock

            def disconnect():
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            job.cancel_io = disconnect
            if job.cancel.is_set():
                disconnect()
                return {"message": {"content": ""}}
            sock.settimeout(timeout)

            def expire():
                deadline_hit.set()
                disconnect()

            timer = threading.Timer(timeout, expire)
            timer.daemon = True
            timer.start()
            body = json.dumps({**payload, "stream": True}).encode()
            connection.request("POST", "/api/chat", body=body, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("Ollama retornou HTTP " + str(response.status) + ": " + response.read(1000).decode(errors="replace"))
            total = 0
            while not job.cancel.is_set():
                line = response.readline(262145)
                if job.cancel.is_set():
                    break
                if deadline_hit.is_set():
                    raise ValueError("Tempo limite do modelo atingido.")
                if not line:
                    break
                total += len(line)
                if len(line) > 262144 or total > 2_000_000:
                    raise ValueError("Resposta do Ollama excedeu o limite.")
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise ValueError(str(chunk["error"]))
                # Only public answer content is used. Private reasoning fields are ignored.
                content = chunk.get("message", {}).get("content", "")
                if not isinstance(content, str):
                    raise ValueError("Conteúdo de resposta inválido.")
                if content:
                    pieces.append(content)
                    on_content("".join(pieces))
                if chunk.get("done"):
                    complete = True
                    break
            if not job.cancel.is_set() and not complete:
                raise ValueError("Tempo limite do modelo atingido." if deadline_hit.is_set() else "Fluxo do modelo terminou antes de concluir a resposta.")
        except (OSError, http.client.HTTPException):
            if not job.cancel.is_set():
                raise ValueError("Tempo limite do modelo atingido." if deadline_hit.is_set() else "Conexão com o Ollama interrompida.")
        finally:
            if timer:
                timer.cancel()
            job.cancel_io = None
            if response:
                response.close()
            connection.close()
        return {"message": {"content": "".join(pieces)}}

    def snapshot(self):
        return copy.deepcopy({"tools": self.catalog, "models": self.models, "checked_at": self.checked_at, "error": self.error, "ollama_url": self.url})

    def get(self, name):
        tool = next((t for t in self.catalog if t["name"] == name), None)
        if not tool:
            raise ValueError("A ferramenta não pertence mais ao catálogo.")
        return tool

    def add(self, name, description):
        resolved = executable(name)
        if any(t["name"] == name for t in self.catalog):
            raise ValueError("Comando já cadastrado.")
        tool = {"name": name, "description": text(description, 2000), "resolved": resolved, "checked_at": now(), "documentation": None}
        self.catalog.append(tool)
        self.save()
        return tool

    def manual(self, name):
        # man is the only implicit documentation subprocess. Never call the tool.
        self.get(name)
        man = shutil.which("man")
        result = run([man, "--", name], timeout=5, output_limit=40000,
                     env={**os.environ, "MANPAGER": "cat", "PAGER": "cat", "MANWIDTH": "100", "MAN_KEEP_FORMATTING": "0"}) if man else {}
        content = re.sub(r".\x08", "", result.get("stdout", ""))[:12000]
        with self.store.lock:
            tool = self.get(name)
            if content.strip() and result.get("exit_code") == 0:
                tool["documentation"] = {"source": "man " + name, "content": content, "at": now(), "sha256": digest(content.encode())}
            else:
                tool["documentation_warning"] = "Manual indisponível. Você pode autorizar uma consulta --help."
            self.save()
        return tool


def target_url(value):
    value = text(value, 2000)
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Porta do alvo inválida.")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Informe uma URL HTTP(S) válida, sem credenciais ou fragmento.")
    return value


def destination_info(args, target):
    parsed = urlsplit(target)
    expected = (parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    found, warnings = [], []
    for arg in args:
        for url in re.findall(r"https?://[^\s\"'<>]+", arg):
            try:
                p = urlsplit(url)
                host = (p.hostname, p.port or (443 if p.scheme == "https" else 80))
                found.append(url)
                if host != expected:
                    warnings.append("URL menciona outro host ou porta: " + url)
            except ValueError:
                warnings.append("Não foi possível interpretar o destino: " + url)
        for host in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", arg):
            if host != expected[0]:
                warnings.append("Possível destino diferente do alvo: " + host)
    for i, arg in enumerate(args):
        if arg in ("-p", "--port", "--ports") and i + 1 < len(args) and args[i + 1] != str(expected[1]):
            warnings.append("A seleção de portas difere da porta do alvo: " + args[i + 1])
    return {"apparent": list(dict.fromkeys(found)), "warnings": list(dict.fromkeys(warnings)),
            "notice": "Detecção indicativa. Revise todos os argumentos: executáveis podem acessar outros destinos ou alterar arquivos. Não há isolamento de rede."}
