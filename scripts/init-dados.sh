#!/usr/bin/env bash
# Prepara dados/ (bind mount persistente) e gera .env com tokens aleatórios. Seguro para rodar mais de uma vez.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p dados/modelos/ollama dados/modelos/importar dados/ferramentas dados/documentacoes dados/__shared__ dados/sessoes dados/banco
chmod 775 dados dados/modelos dados/modelos/ollama dados/sessoes dados/banco 2>/dev/null || true

if [ ! -f .env ]; then
  gerar() { python3 -c 'import secrets; print(secrets.token_hex(24))'; }
  sed -e "s/^PLATAFORMA_UID=.*/PLATAFORMA_UID=$(id -u)/" \
      -e "s/^PLATAFORMA_GID=.*/PLATAFORMA_GID=$(id -g)/" \
      -e "s/^EXECUTOR_TOKEN=.*/EXECUTOR_TOKEN=$(gerar)/" \
      -e "s/^RESET_TOKEN=.*/RESET_TOKEN=$(gerar)/" \
      .env.example > .env
  if getent group docker >/dev/null 2>&1; then
    sed -i "s/^DOCKER_GID=.*/DOCKER_GID=$(getent group docker | cut -d: -f3)/" .env
  fi
  chmod 600 .env
  echo ".env criado (UID/GID $(id -u):$(id -g), tokens aleatórios)."
else
  echo ".env já existe; mantido."
fi

cat <<MSG

Pronto. Próximos passos:
  1. docker compose up -d --build                      # alvo na LAN
     docker compose --profile local up -d --build      # ou: com o Juice Shop local (defina RESET_URL=http://juice-reset:9000 no .env)
  2. sudo ./scripts/aplicar-egress.sh --modo lan --alvo <IP-do-Juice-Shop> --portas 3000     # restringe a saída do executor
  3. Abra http://127.0.0.1:8080 e siga as instruções de modelos e ferramentas (README.md).
MSG
