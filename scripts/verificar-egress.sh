#!/usr/bin/env bash
# Pede ao executor que TENTE conectar a destinos que devem estar bloqueados (e ao alvo da sessão, se informado).
#   ./scripts/verificar-egress.sh [SESSAO_ID] [IP:PORTA ...]
# O teste é parcial: não prova ausência de outros caminhos de saída.
set -euo pipefail
PORTA="${UI_PORTA:-8080}"
SESSAO="${1:-}"; shift || true
python3 - "$PORTA" "$SESSAO" "$@" <<'PY'
import json, sys, urllib.request
porta, sessao, extras = sys.argv[1], sys.argv[2] or None, sys.argv[3:]
req = urllib.request.Request(f"http://127.0.0.1:{porta}/api/egress/verificar", method="POST",
    data=json.dumps({"sessao_id": sessao, "destinos_extra": extras}).encode(), headers={"Content-Type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=90))
for x in r["resultados"]:
    estado = "ALCANÇOU" if x["alcancou"] else "bloqueado/sem resposta"
    print(f'{x["ip"]}:{x["porta"]:<6} {x["rotulo"]:<40} -> {estado}')
print("\nOK: nenhum destino proibido foi alcançado." if r["ok"] else "\nATENÇÃO: algum destino proibido foi alcançado!")
print(r["aviso"])
sys.exit(0 if r["ok"] else 1)
PY
