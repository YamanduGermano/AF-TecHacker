import json
import mimetypes
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import reports
from .storage import encode

STATIC = Path(__file__).parent / "static"


def handler_for(service, port):
    csrf = secrets.token_urlsafe(32)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "Laboratorio/1.0"

        def log_message(self, format, *args):
            # Do not write user inputs, command arguments or tokens into access logs.
            pass

        def send(self, status, body, mime="application/json; charset=utf-8", filename=None, artifact=None):
            if not isinstance(body, bytes):
                body = encode(body)
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            if artifact:
                self.send_header("X-Lab-Artifact-ID", artifact["id"])
                self.send_header("X-Content-SHA256", artifact["sha256"])
            self.end_headers()
            self.wfile.write(body)

        def check(self, mutate=False):
            host = self.headers.get("Host", "")
            if host not in hosts:
                raise PermissionError("Host não autorizado. Abra o endereço local informado no terminal.")
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + host:
                raise PermissionError("Origem não autorizada.")
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise PermissionError("Solicitação externa recusada.")
            if mutate and not secrets.compare_digest(self.headers.get("X-Lab-Token", ""), csrf):
                raise PermissionError("Token inválido. Recarregue a página.")

        def do_GET(self):
            try:
                self.check()
                path = urlsplit(self.path).path
                parts = path.strip("/").split("/")
                if path == "/api/bootstrap":
                    with service.store.lock:
                        return self.send(200, {"token": csrf, "resources": service.resources.snapshot(), "sessions": service.store.list()})
                if path == "/api/skills":
                    with service.store.lock:
                        return self.send(200, service.skills.catalog())
                if len(parts) >= 3 and parts[:2] == ["api", "sessions"]:
                    with service.store.lock:
                        s = service.store.get(parts[2])
                        if len(parts) == 3:
                            return self.send(200, s)
                        if len(parts) == 5 and parts[3] == "preview" and parts[4] in ("logs", "chat", "report"):
                            data, _, filename = reports.export(service.store, s, parts[4])
                            return self.send(200, {"name": filename, "content": data[:262144].decode("utf-8", errors="replace"), "truncated": len(data) > 262144, "bytes": len(data), "origin": "Registros atuais da sessão"})
                        if len(parts) == 5 and parts[3] == "export":
                            data, mime, filename = reports.export(service.store, s, parts[4])
                            artifact = service.store.artifact(s, filename, data, "exportação " + parts[4])
                            service.store.event(s, "export", "Exportação gerada: " + filename, artifact_id=artifact["id"])
                            service.store.save(s)
                            return self.send(200, data, mime, filename, artifact)
                        if len(parts) in (5, 6) and parts[3] == "artifacts":
                            a = next((a for a in s["artifacts"] if a["id"] == parts[4]), None)
                            if not a:
                                raise ValueError("Arquivo não encontrado.")
                            file = service.store.directory(s["id"]) / "arquivos" / a["name"]
                            from .storage import digest
                            data = file.read_bytes()
                            if digest(data) != a["sha256"]:
                                raise ValueError("Arquivo alterado: hash divergente.")
                            if len(parts) == 6:
                                if parts[5] != "view":
                                    raise ValueError("Visualização desconhecida.")
                                if a["name"].endswith(".zip"):
                                    import io
                                    import zipfile
                                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                                        entries = archive.infolist()
                                        content = "Conteúdo do pacote ZIP:\n\n" + "\n".join(f"{item.filename} ({item.file_size} bytes)" for item in entries[:200])
                                    return self.send(200, {**a, "content": content, "truncated": len(entries) > 200})
                                snippet = data[:262144]
                                binary = b"\x00" in snippet
                                return self.send(200, {**a, "content": "Arquivo binário. Use o download para abrir no aplicativo apropriado." if binary else snippet.decode("utf-8", errors="replace"), "truncated": len(data) > len(snippet), "binary": binary})
                            return self.send(200, data, "application/octet-stream", a["name"])
                if path in ("/", "/index.html", "/styles.css", "/app.js", "/favicon.svg"):
                    file = STATIC / ("index.html" if path == "/" else path.lstrip("/"))
                    return self.send(200, file.read_bytes(), mimetypes.guess_type(file)[0] or "text/plain")
                self.send(404, {"error": "Rota não encontrada."})
            except PermissionError as exc:
                self.send(403, {"error": str(exc)})
            except (ValueError, FileNotFoundError) as exc:
                self.send(400, {"error": str(exc)})

        def do_POST(self):
            try:
                self.check(mutate=True)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Envie JSON.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 100000:
                    raise ValueError("Corpo ausente ou maior que 100 KB.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Objeto JSON esperado.")
                path = urlsplit(self.path).path
                parts = path.strip("/").split("/")
                result = None
                if path == "/api/resources/refresh":
                    result = service.resources.refresh()
                elif path == "/api/skills/add":
                    with service.store.lock:
                        result = service.skills.add(data)
                elif path == "/api/tools/add":
                    with service.store.lock:
                        tool = service.resources.add(data.get("name"), data.get("description", ""))
                    service.resources.manual(tool["name"])
                    result = service.resources.snapshot()
                elif path == "/api/tools/remove":
                    with service.store.lock:
                        service.resources.get(data.get("name"))
                        service.resources.catalog = [t for t in service.resources.catalog if t["name"] != data["name"]]
                        service.resources.save()
                        result = service.resources.snapshot()
                elif path == "/api/tools/manual":
                    service.resources.manual(data.get("name"))
                    result = service.resources.snapshot()
                elif path == "/api/help/prepare":
                    result = service.prepare_help(data.get("name"))
                elif len(parts) == 4 and parts[:2] == ["api", "help"] and parts[3] == "approve":
                    result = service.approve_help(parts[2], data)
                elif path == "/api/sessions":
                    result = service.create_session(data)
                elif len(parts) >= 4 and parts[:2] == ["api", "sessions"]:
                    sid, action = parts[2:4]
                    if len(parts) == 4:
                        if action == "ask":
                            result = service.ask(sid, data)
                        elif action == "stop":
                            result = service.stop(sid)
                        elif action == "update":
                            result = service.update(sid, data)
                        elif action == "restore":
                            result = service.restore(sid, data)
                        elif action == "skills":
                            result = service.skill_action(sid, data)
                        elif action == "manual-preview":
                            result = service.manual_command(sid, data)
                        elif action == "manual-run":
                            result = service.manual_command(sid, data, execute=True)
                    elif len(parts) == 6 and action == "proposals":
                        result = service.proposal_action(sid, parts[4], parts[5], data)
                    elif len(parts) == 5 and action == "revisions":
                        result = service.revision(sid, parts[4], data)
                if result is None:
                    return self.send(404, {"error": "Rota não encontrada."})
                self.send(200, result)
            except PermissionError as exc:
                self.send(403, {"error": str(exc)})
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                self.send(400, {"error": str(exc)})
            except Exception:
                self.send(500, {"error": "Falha interna. Os registros anteriores foram preservados; verifique a operação e o diretório de dados."})

    return Handler


def create_server(service, port):
    server = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    server.RequestHandlerClass = handler_for(service, server.server_port)
    server.daemon_threads = True
    return server
