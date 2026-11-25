#!/usr/bin/env python3
"""Scanner de portas SIMULADO (só para testes): não abre nenhuma conexão."""
import sys

a = sys.argv[1:]
portas = a[a.index("-p") + 1].split(",") if "-p" in a else []
alvo = a[-1]
print(f"Starting Nmap (fake) scan report for {alvo}")
print("Host is up (0.00010s latency).")
print("PORT     STATE  SERVICE")
for p in portas:
    estado = "open" if p == "3000" else "closed"
    print(f"{p}/tcp  {estado}  {'http' if estado == 'open' else 'unknown'}")
print("Nmap done: 1 IP address (1 host up) scanned")
