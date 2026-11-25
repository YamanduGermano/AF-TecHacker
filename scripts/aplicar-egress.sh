#!/usr/bin/env bash
# Restringe a saída da rede do executor (rede Docker 'rede_alvo', ponte br-alvo-lab) ao alvo autorizado.
#
#   sudo ./scripts/aplicar-egress.sh --modo lan   --alvo 192.168.1.50 --portas 3000
#   sudo ./scripts/aplicar-egress.sh --modo local                       # só a própria sub-rede (serviço juice-shop)
#   sudo ./scripts/aplicar-egress.sh --remover
#
# O que faz (iptables, cadeia DOCKER-USER para tráfego encaminhado e INPUT para tráfego destinado ao próprio host):
#   permite respostas de conexões já estabelecidas; permite SOMENTE <alvo>:<portas> (modo lan) e a própria
#   sub-rede da rede_alvo; registra e descarta o resto.
# Limitações (leia o README): não cobre DNS pelo resolvedor embutido do Docker (use compose.dns-bloqueado.yaml),
# IPv6 (desabilitado por padrão no Docker) nem hosts com nftables puro sem a camada de compatibilidade iptables.
set -euo pipefail

SUBNET="${REDE_ALVO_SUBNET:-172.30.77.0/24}"
BR="br-alvo-lab"
MODO="" ALVO="" PORTAS="" REMOVER=0

while [ $# -gt 0 ]; do
  case "$1" in
    --modo) MODO="$2"; shift 2;;
    --alvo) ALVO="$2"; shift 2;;
    --portas) PORTAS="$2"; shift 2;;
    --sub-rede) SUBNET="$2"; shift 2;;
    --remover) REMOVER=1; shift;;
    -h|--help) sed -n '2,15p' "$0"; exit 0;;
    *) echo "argumento desconhecido: $1" >&2; exit 2;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "execute como root (sudo)." >&2; exit 1; }
command -v iptables >/dev/null || { echo "iptables não encontrado." >&2; exit 1; }

limpar() {
  for cadeia in DOCKER-USER INPUT; do
    while iptables -C "$cadeia" -s "$SUBNET" -j PLATAFORMA-EGRESS 2>/dev/null; do iptables -D "$cadeia" -s "$SUBNET" -j PLATAFORMA-EGRESS; done
  done
  if iptables -L PLATAFORMA-EGRESS -n >/dev/null 2>&1; then iptables -F PLATAFORMA-EGRESS; iptables -X PLATAFORMA-EGRESS; fi
}

limpar
if [ "$REMOVER" -eq 1 ]; then echo "regras de egress removidas."; exit 0; fi

case "$MODO" in
  lan)
    [[ "$ALVO" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "--alvo deve ser um IPv4 (ex.: 192.168.1.50)." >&2; exit 2; }
    [ -n "$PORTAS" ] || { echo "--portas obrigatório (ex.: 3000 ou 3000,443)." >&2; exit 2;};;
  local) ;;
  *) echo "use --modo lan|local" >&2; exit 2;;
esac

iptables -N PLATAFORMA-EGRESS
iptables -A PLATAFORMA-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A PLATAFORMA-EGRESS -d "$SUBNET" -j RETURN          # tráfego dentro da própria rede_alvo (juice-shop local)
if [ "$MODO" = "lan" ]; then
  IFS=',' read -ra LISTA <<< "$PORTAS"
  for p in "${LISTA[@]}"; do
    [[ "$p" =~ ^[0-9]{1,5}$ ]] || { echo "porta inválida: $p" >&2; exit 2; }
    iptables -A PLATAFORMA-EGRESS -d "$ALVO" -p tcp --dport "$p" -j RETURN
  done
fi
iptables -A PLATAFORMA-EGRESS -m limit --limit 6/min -j LOG --log-prefix "plataforma-egress-bloqueado: " --log-level 4
iptables -A PLATAFORMA-EGRESS -j DROP

# Tráfego encaminhado (para a LAN/internet) e tráfego para serviços do próprio host.
iptables -I DOCKER-USER -s "$SUBNET" -j PLATAFORMA-EGRESS
iptables -I INPUT -s "$SUBNET" -j PLATAFORMA-EGRESS

echo "egress aplicado: sub-rede $SUBNET -> ${ALVO:-somente a própria sub-rede}${PORTAS:+ portas $PORTAS}"
echo "Verifique com ./scripts/verificar-egress.sh (ou o botão 'Verificar saída de rede' da interface)."
