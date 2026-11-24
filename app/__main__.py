import argparse
import os
import signal
from pathlib import Path

from .server import create_server
from .service import Service


def main():
    if os.name != "posix":
        raise SystemExit("Use Linux, macOS ou WSL2. O executor requer grupos de processos POSIX.")
    parser = argparse.ArgumentParser(description="Laboratório local — Tecnologias Hackers")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "dados"))
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Porta inválida.")
    service = Service(args.data_dir, args.ollama_url)
    service.resources.refresh()
    server = create_server(service, args.port)
    print(f"Laboratório aberto em http://127.0.0.1:{args.port}", flush=True)
    print("Use Ctrl+C para encerrar. Nenhum comando executa sem aprovação individual.", flush=True)

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        from .executor import terminate
        for sid, job in list(service.jobs.items()):
            service.stop(sid)
            terminate(job.process)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
