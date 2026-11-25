#!/usr/bin/env python3
"""Cliente HTTP SIMULADO (só para testes): imita as opções do curl usadas pelo adaptador.

Não faz nenhuma requisição de rede; responde conteúdo fixo conforme o caminho.
"""
import re
import sys
import time

a = sys.argv[1:]
urls = [x for x in a if re.match(r"^https?://", x)]
url = urls[-1] if urls else ""
fmt = a[a.index("-w") + 1] if "-w" in a else ""
metodo = "HEAD" if "-I" in a else (a[a.index("-X") + 1] if "-X" in a else "GET")
caminho = re.sub(r"^https?://[^/]+", "", url)
host_resolvido = ""
if "--resolve" in a:
    host_resolvido = a[a.index("--resolve") + 1].rsplit(":", 1)[-1]

if "SLEEP" in caminho:
    time.sleep(60)
if "BIG" in caminho:
    sys.stdout.write("HTTP/1.1 200 OK\r\n\r\n" + "x" * 3_000_000)
    sys.exit(0)

status = 404 if caminho.startswith("/missing") else 200
corpo = f"<html><head><title>OWASP Juice Shop</title></head><body>caminho={caminho} metodo={metodo}</body></html>"
cab = f"HTTP/1.1 {status} OK\r\nContent-Type: text/html\r\nSet-Cookie: token=segredo123\r\nServer: fake\r\n\r\n"
sys.stdout.write(cab + ("" if metodo == "HEAD" else corpo))
ip = ""
m = re.search(r"https?://\[?([^/\]:]+)", url)
alvo_ip = host_resolvido.strip("[]") or (m.group(1) if m else "")
meta = (fmt.replace("\\n", "\n").replace("%{http_code}", str(status)).replace("%{time_total}", "0.012")
        .replace("%{remote_ip}", alvo_ip).replace("%{remote_port}", "3000")
        .replace("%{size_download}", str(len(corpo))))
sys.stdout.write(meta)
