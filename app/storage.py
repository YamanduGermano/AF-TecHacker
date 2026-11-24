import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sessoes").mkdir(exist_ok=True)
        self.lock = threading.RLock()

    def write(self, path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + "." + uid() + ".tmp")
        with temp.open("wb") as f:
            f.write(encode(value))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)

    def directory(self, sid):
        if not re.fullmatch(r"[a-f0-9]{32}", sid):
            raise ValueError("Identificador de sessão inválido.")
        return self.root / "sessoes" / sid

    def get(self, sid):
        path = self.directory(sid) / "sessao.json"
        if not path.exists():
            raise ValueError("Sessão não encontrada.")
        return json.loads(path.read_text())

    def save(self, session):
        session["updated_at"] = now()
        self.write(self.directory(session["id"]) / "sessao.json", session)

    def list(self):
        items = []
        for path in (self.root / "sessoes").glob("*/sessao.json"):
            s = json.loads(path.read_text())
            items.append({k: s[k] for k in ("id", "title", "target", "model", "updated_at", "status")})
        return sorted(items, key=lambda s: s["updated_at"], reverse=True)

    def event(self, session, kind, message, **extra):
        session["events"].append({"id": uid(), "at": now(), "kind": kind, "message": message, **extra})

    def artifact(self, session, filename, data, origin):
        aid = uid()
        name = aid[:8] + "-" + Path(filename).name
        path = self.directory(session["id"]) / "arquivos" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        record = {"id": aid, "name": name, "origin": origin, "sha256": digest(data), "bytes": len(data), "at": now()}
        session["artifacts"].append(record)
        return record
