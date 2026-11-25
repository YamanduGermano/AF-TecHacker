"""Serviço mínimo de restauração do Juice Shop LOCAL.

Faz exatamente uma coisa: reiniciar o contêiner fixo ALVO_CONTAINER pela API do Docker. Nenhum dado da
requisição entra na chamada. Só o agente (que conhece RESET_TOKEN) o alcança, pela rede interna.
O Juice Shop recria seu banco ao iniciar; reiniciar o contêiner o devolve ao estado inicial.
"""
import hmac
import http.client
import json
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer

ALVO = os.environ.get("ALVO_CONTAINER", "juice-shop-lab")
TOKEN = os.environ.get("RESET_TOKEN", "")
assert re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", ALVO), "ALVO_CONTAINER inválido"
assert TOKEN, "RESET_TOKEN obrigatório"


class ConexaoUnix(http.client.HTTPConnection):
    def __init__(self, caminho: str):
        super().__init__("docker")
        self._caminho = caminho

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(self._caminho)


class Handler(BaseHTTPRequestHandler):
    def _responder(self, codigo: int, corpo: dict):
        dados = json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_POST(self):
        if self.path != "/reset":
            return self._responder(404, {"erro": "não encontrado"})
        if not hmac.compare_digest(self.headers.get("X-Reset-Token", ""), TOKEN):
            return self._responder(401, {"erro": "token inválido"})
        try:
            c = ConexaoUnix("/var/run/docker.sock")
            c.request("POST", f"/containers/{ALVO}/restart?t=3")
            r = c.getresponse()
            r.read()
            if r.status not in (204, 200):
                return self._responder(502, {"erro": f"docker respondeu {r.status}"})
        except OSError as e:
            return self._responder(502, {"erro": str(e)})
        return self._responder(200, {"ok": True, "reiniciado": ALVO})

    def do_GET(self):
        self._responder(200, {"ok": True})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
