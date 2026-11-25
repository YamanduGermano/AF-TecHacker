# Plataforma de agente supervisionado — laboratório OWASP Juice Shop

Plataforma para um exercício acadêmico (Insper — *Tecnologias Hackers*): um **modelo de linguagem local propõe** ações de
teste sobre **uma instância autorizada do OWASP Juice Shop** e **o grupo decide cada ação** (autorizar, editar e autorizar,
rejeitar). Nada é executado sem decisão humana específica, tudo fica registrado e uma afirmação do modelo nunca é tratada como
evidência.

> **Uso autorizado.** Use somente contra a instância do Juice Shop do laboratório (ou a local, opcional). O escopo é fixado na
> criação da sessão (URL, IP e porta); a plataforma recusa outros hosts, portas e IPs — mas a barreira técnica depende também
> da rede (seção 7). Informar uma URL não autoriza testar outros equipamentos da LAN nem serviços externos.

**O que este pacote contém:** código e configuração da plataforma. **Não contém** pesos de modelo, executáveis de ferramentas,
documentações de ferramentas, resultados de investigações, relatório final nem vídeo. Esses itens são fornecidos por você depois
(seções 3 e 4).

---

## 1. Arquitetura

```
 navegador ──► web-ui (nginx, 127.0.0.1:8080) ──► agente (API + proxy de política + armazenamento) ──► ollama
                                                      │                                            (sem internet)
                                                      └──► executor ──► alvo autorizado (IP:porta fixados)
                                                           (rede restrita, somente leitura, sem docker.sock)
```

| Serviço | Função | Rede |
|---|---|---|
| `web-ui` | Interface (HTML/JS puro, CSP restritiva). **Única porta publicada**, em `127.0.0.1`. | `rede_frontend` + `rede_interna` |
| `agente` | API, orquestração, **proxy de política** (`proxy/`), descoberta de recursos, registros, exportação, relatório. | `rede_interna` (sem rota para a LAN) |
| `ollama` | Inferência local. Sem porta publicada e **sem internet**. | `rede_interna` (`internal: true`) |
| `executor` | Único componente que executa ferramentas; monta `dados/ferramentas` só-leitura; revalida política e hashes antes de rodar. | `rede_interna` + `rede_alvo` |
| `juice-shop` *(perfil `local`)* | Juice Shop opcional. | `rede_alvo` |
| `juice-reset` *(perfil `local`)* | Sidecar mínimo que apenas reinicia o contêiner `juice-shop-lab`. | `rede_interna` |

Divisão de responsabilidades: `proxy/` (contratos, política, runner), `executor/` (serviço e adaptadores), `agente/`
(app, orquestrador, descoberta, armazenamento, relatório), `web_ui/`, `reset/`, `scripts/`, `tests/`, `exemplos/`.

## 2. Requisitos

* Docker Engine + Docker Compose v2. Recomendado: **Linux** (ou WSL2 no Windows). Memória: o `ollama` usa até
  `OLLAMA_MEM_LIMIT` (padrão 8 GB) — ajuste ao tamanho do seu modelo.
* Python 3.11+ somente para rodar os testes (seção 12).
* Para restringir a saída do executor no host: Linux com `iptables` e `sudo` (seção 7).

## 3. Início rápido (com `dados/` vazio)

```bash
./scripts/init-dados.sh                     # cria dados/…, gera .env com tokens aleatórios e o UID/GID do seu usuário
docker compose up -d --build                # alvo = Juice Shop que já existe na LAN
# ou, com o Juice Shop local opcional:
#   (no .env) RESET_URL=http://juice-reset:9000
#   docker compose --profile local up -d --build
```

Abra **http://127.0.0.1:8080**. Com `dados/` vazio a interface sobe normalmente e mostra **«sem modelos»** e
**«sem ferramentas»** com as instruções de instalação; já é possível configurar o alvo e validá-lo.

Fluxo na interface: **Verificar novos recursos → selecionar modelo → revisar e habilitar ferramentas → Nova sessão (validar
alvo) → plano humano → consultar o modelo → decidir cada ação → registrar evidências → exportar / rascunho do relatório.**

### Modo LAN × modo local

| | **LAN** | **Local (opcional)** |
|---|---|---|
| Alvo | URL completa informada por você (ex.: `http://192.168.1.50:3000/`) + confirmação de que é instância autorizada | `juice-shop` do Compose (`--profile local`) |
| Restrição de saída | `sudo ./scripts/aplicar-egress.sh --modo lan --alvo 192.168.1.50 --portas 3000` | `sudo ./scripts/aplicar-egress.sh --modo local` |
| Reset do alvo | **Procedimento humano registrado**: você restaura o alvo no computador dele e descreve o que fez | Automatizado pelo `juice-reset` (reinicia só `juice-shop-lab`) |

A plataforma **não depende** do Juice Shop local para ser configurada.

## 4. Modelos

Só aparecem como **utilizáveis** os modelos **registrados no Ollama e validados pela API dele**. A seleção e a troca são
explícitas e registradas; uma sessão em andamento **nunca** muda de modelo sozinha (o *digest* é fixado por sessão).

**Opção A — `ollama pull`** (a internet é dada apenas a esse comando, por `compose.pull.yaml`):

```bash
docker compose -f compose.yaml -f compose.pull.yaml run --rm ollama-pull ollama pull <modelo>
```

**Opção B — GGUF local:** copie `meu-modelo.gguf` e `meu-modelo.Modelfile` (com `FROM meu-modelo.gguf`; veja
`exemplos/modelos/exemplo.Modelfile`) para `dados/modelos/importar/`. Depois: **Verificar novos recursos → Importar**. A
plataforma confere a assinatura GGUF e que o `FROM` aponta para o mesmo arquivo, e só então registra no Ollama. (Outros
formatos, como safetensors, não são importados por esta plataforma: converta antes.)

Trocar de modelo numa sessão que já tem interações exige **confirmação**: o contexto anterior é arquivado (continua nos
registros e exportações) e o novo modelo começa sem ele.

Modelos pequenos erram o protocolo JSON com frequência; a plataforma tenta **uma** correção automática e registra as respostas
inválidas — isso também alimenta a análise crítica da IA no relatório.

## 5. Ferramentas, documentação e manifestos

Estrutura (tudo dentro de `dados/`, **fora das imagens**):

```
dados/ferramentas/<id>/manifest.json   +   dados/ferramentas/<id>/<executável>   (chmod 755)
dados/documentacoes/<id>.md            (propósito, exemplos, parâmetros, interpretação dos resultados)
dados/__shared__/                      (candidatas: são detectadas, nunca executadas nem habilitadas)
```

Veja `exemplos/ferramentas/*/manifest.json` (**não executáveis**) e `exemplos/documentacoes/*.md`.

**Perfis (adaptadores) reconhecidos:** `http_client_curl` e `port_scanner_nmap`. Perfil desconhecido fica **indisponível**
até existir um adaptador específico revisado em `executor/adapters.py`. O modelo escolhe um `id` habilitado e envia **parâmetros
estruturados** (por exemplo `metodo`, `caminho`); não existe campo de host, porta, URL absoluta, proxy, script ou flags.
O `argv` é montado pelo adaptador, sem shell (`shell=False`).

**Fornecendo os executáveis.** A imagem do executor **não** traz curl/nmap. Duas formas:

1. binário **estático** copiado para `dados/ferramentas/<id>/` e referenciado no manifesto; ou
2. definir `EXECUTOR_EXTRA_APT=curl` (ou `nmap`) no `.env`, `docker compose build executor`, e usar o invólucro de duas linhas
   `exemplos/ferramentas/<id>/executar.sh.exemplo` (renomeie para `executar.sh`, `chmod 755`). **Atenção:** nesse caso o hash
   registrado é o do invólucro, não o do binário do sistema.

**Habilitação.** *Verificar novos recursos → Revisar → Habilitar*. Só é possível com manifesto válido, documentação presente e
perfil aceito. A habilitação grava os hashes SHA-256 de manifesto, executável e documentação; **qualquer alteração posterior
suspende** a ferramenta (`suspensa_alterada`) até nova revisão. Os hashes são conferidos de novo, sem cache, antes de cada
execução e ficam registrados em cada ação.

**Varredura.** Roda ao iniciar e sob demanda («Verificar novos recursos»). Mostra progresso, itens novos/alterados/removidos,
erros e avisos de documentação ausente. **Nunca executa** binários novos nem ativa recursos sozinha.

## 6. Como a plataforma controla cada ação

1. **Plano humano primeiro:** o modelo só é consultado depois que o plano (5 campos) é salvo; as versões do plano são preservadas.
2. O modelo responde com **um objeto JSON** (`proposta`, `mensagem`, `revisao_plano` ou `concluir`). Sugestões do modelo sobre o
   plano são aceitas, alteradas ou rejeitadas **com justificativa**.
3. A **política** é aplicada ao exibir a proposta e **de novo imediatamente antes de executar** (inclusive após edição humana):
   ferramenta habilitada e íntegra, esquema dos parâmetros, caminho relativo, método (GET/HEAD por padrão), cabeçalhos em lista
   permitida (`Host` nunca), alvo fixado pelo backend (IP resolvido na sessão, conexão por `--resolve`, revalidação contra
   *DNS rebinding*, sem redirecionamentos), limites de passos (25), taxa (20/min), tempo, tamanho e concorrência.
4. **Decisão por ação:** *Autorizar*, *Editar e autorizar* (parâmetros revalidados) ou *Rejeitar* (não executa). Ações
   **bloqueadas** também ficam registradas.
5. Saídas de ferramentas, páginas e cabeçalhos são **dados não confiáveis**: instruções vindas do alvo não mudam a política nem
   dispensam a aprovação.

## 7. Restrição de saída do executor (importante)

O Docker, sozinho, não limita o destino da conexão. Para o modo LAN existe `scripts/aplicar-egress.sh` (iptables em
`DOCKER-USER` e `INPUT`, sub-rede `172.30.77.0/24`, ponte `br-alvo-lab`): permite respostas estabelecidas e **somente**
`<alvo>:<portas>`; registra e descarta o resto.

```bash
sudo ./scripts/aplicar-egress.sh --modo lan --alvo 192.168.1.50 --portas 3000
./scripts/verificar-egress.sh                   # ou o botão «Verificar saída de rede» da interface
sudo ./scripts/aplicar-egress.sh --remover
```

**Limitações — leia:**

* O teste (script ou botão) tenta alcançar alguns destinos proibidos e o alvo; **não prova** que não existam outros caminhos de
  saída. A interface avisa isso.
* **DNS:** o resolvedor embutido do Docker não passa pelo firewall do host. Para o modo LAN, use o **IP** na URL e, opcionalmente,
  `docker compose -f compose.yaml -f compose.dns-bloqueado.yaml up -d`.
* **IPv6** (desligado por padrão no Docker) e hosts só com nftables sem a camada de compatibilidade iptables **não** são cobertos.
* Se o Juice Shop roda **no mesmo computador** do Docker, o tráfego chega pela cadeia `INPUT` (coberta pelo script).
* **Docker Desktop (macOS/Windows):** a rede Docker vive numa VM; o script não filtra isso a partir do host. Aplique a restrição na
  VM, num gateway/ACL da rede do laboratório ou rode a plataforma numa VM Linux.

### Topologia sugerida (a decidir no seu laboratório)

* **Kali (VM) → UI:** a interface escuta só em `127.0.0.1`. Se o navegador está em outra máquina, use
  `ssh -L 8080:127.0.0.1:8080 usuario@host-docker` (evite publicar a UI na LAN).
* **Host Docker e computador do Juice Shop** na mesma rede protegida; regras de egress no host Docker (ou no gateway) permitindo
  apenas o IP/porta do Juice Shop.
* O agente e o Ollama ficam em rede `internal`: não alcançam LAN nem internet.

## 8. Permissões do bind mount (`dados/`) por sistema operacional

Os contêineres rodam como `PLATAFORMA_UID:PLATAFORMA_GID` (o `init-dados.sh` usa o seu usuário).

* **Linux:** `dados/` deve pertencer a esse usuário; executáveis com `chmod 755` e legíveis. Se houver SELinux, adicione `:z` aos
  volumes ou ajuste o contexto.
* **WSL2 (Windows):** mantenha o projeto **dentro do sistema de arquivos do WSL** (`~/plataforma`), **não** em `/mnt/c/…`
  (bits de execução, permissões e SQLite ficam instáveis em NTFS).
* **macOS (Docker Desktop):** `PLATAFORMA_UID=$(id -u)`; compartilhe a pasta do projeto nas configurações do Docker.
* Se a interface mostrar erro de escrita em `dados/sessoes` ou `dados/banco`, o dono/permissão da pasta não corresponde ao UID do `.env`.
* Os arquivos que você adiciona ao bind mount **sobrevivem** à recriação dos contêineres (`docker compose down && up`).

## 9. Registros, evidências, exportação e relatório

* **Eventos** encadeados (`anterior_id`) com sessão, investigação, data/hora e objetivo; texto da proposta, parâmetros originais e
  efetivos, decisão e justificativa, validações, chamada executada, código de saída, resumo para o modelo, interpretação do modelo e
  notas posteriores do grupo. Ações bloqueadas também entram.
* **Resultados brutos** em arquivos imutáveis (somente leitura, nome seguro, tamanho e **SHA-256**).
* Credenciais/tokens são **ocultados na interface e nas exportações**; o registro interno preserva o original para análise.
* **Downloads** (por sessão, nunca de outra): `chat`, `eventos`, `arquivos` (ZIP com `MANIFESTO-HASHES.json`), `resultados`,
  `relatorio` (Markdown) e `completo`. Funcionam mesmo se a investigação terminou sem conclusão ou faltam investigações.
* **Rascunho do relatório** (Markdown, editável na interface): preenche **só** o que existe nos registros; o resto vira
  `[PENDENTE]`. Conclusão de investigação só aparece se houver evidência registrada que a sustente. Análise crítica da IA e erro
  concreto da IA ficam para o grupo escrever (com candidatos extraídos dos registros). Até **3 investigações** por sessão.
* **Reset:** em cada investigação, restaure o alvo antes de começar (botão **Restaurar alvo**); a restauração fica registrada.

## 10. Segurança: o que a plataforma garante e o que não garante

Garante (verificado por testes automatizados com recursos simulados): decisão humana por ação; política antes de exibir e antes de
executar; bloqueio de outro host/porta/IP, `Host` arbitrário, proxies, redirecionamentos e parâmetros proibidos (inclusive vindos de
manifestos); integridade por hash; executor sem shell, com limites de tempo/saída/concorrência e `killpg` em excesso; exportação
sem *symlinks* e restrita à sessão.

Não garante: que um binário fornecido por você respeite o escopo (por isso o escopo é imposto por adaptador revisado e pela
rede); isolamento de rede sem as regras de egress; ausência de outros caminhos de saída. **Exceção consciente à §7 da
especificação:** o `docker.sock` é montado **apenas** no sidecar `juice-reset` (perfil `local`), que só reinicia o contêiner
`juice-shop-lab`; o executor não monta `docker.sock`, não é privilegiado e roda sem capabilities.

## 11. Limites padrão e variáveis (`.env`)

`MAX_PASSOS_POR_INVESTIGACAO=25`, `MAX_CHAMADAS_POR_MINUTO=20`, `MAX_TIMEOUT_S=60`, `METODOS_PERMITIDOS=GET,HEAD`,
`PERMITIR_CORPO_REQUISICAO=false`, `PERMITIR_ALVOS_PUBLICOS=false`, `OLLAMA_MEM_LIMIT=8g`, `EXECUTOR_MEM_LIMIT=1g`,
`EXECUTOR_CPUS=2`, `AGENTE_MEM_LIMIT=1g`, `UI_PORTA=8080`. O manifesto de uma ferramenta nunca pode exceder a política global.
Veja `.env.example`.

## 12. Testes

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest                      # Ollama, ferramentas e alvo SIMULADOS: sem rede, sem Docker, sem modelos
```

Cobrem os critérios de aceitação da especificação (§10): estado vazio, recursos fora da imagem, varredura (adição/alteração/remoção
sem executar nada), modelo só após registro/validação e troca explícita, habilitação e suspensão de ferramentas, plano antes do
modelo, aprovação por ação, edição revalidada, rejeição sem execução, bloqueio de outro host/porta/IP, exportações e rascunho.

Teste de fumaça opcional da interface (navegador headless + backend simulado):
`pip install playwright && playwright install chromium && python tests/ui_smoke.py`.

## 13. O que NÃO foi verificado (seja honesto no seu relatório)

O ambiente em que o código foi escrito **não tinha daemon Docker**. Portanto:

* As **imagens não foram construídas** nem os contêineres iniciados; os arquivos Compose foram validados só por sintaxe
  (`docker compose config`). Pode haver ajustes de permissões, de nomes de pacotes ou de saúde dos serviços no primeiro `up`.
* `scripts/aplicar-egress.sh`, `scripts/verificar-egress.sh` e o sidecar `juice-reset` **não foram executados** contra sistemas reais
  (apenas checagem de sintaxe do shell).
* A **API real do Ollama** (`/api/tags`, `/api/show`, `/api/blobs`, `/api/create`) e a invocação **real** de curl/nmap foram
  exercitadas só com simulações; versões diferentes do Ollama podem exigir pequenos ajustes na importação de GGUF.
* Nenhum modelo real foi usado: a qualidade das propostas e a aderência ao protocolo JSON dependem do modelo que você instalar.

## 14. Fora do escopo desta entrega (etapa sua, depois)

Instalar modelos e executáveis, escrever as documentações, habilitar **pelo menos duas** ferramentas, realizar **três**
investigações distintas, documentar a restauração do Juice Shop, produzir análise crítica, relatório final de 4 a 6 páginas e o
vídeo de até 10 minutos. A plataforma apenas dá suporte a isso.

## 15. Decisões de projeto (§11 da especificação)

| Tema | Decisão |
|---|---|
| Topologia | Kali/navegador → UI em `127.0.0.1` (túnel SSH se remoto); host Docker na LAN do laboratório; egress restrito ao IP:porta do alvo |
| Restrição de saída | `iptables` (`DOCKER-USER` + `INPUT`) no host Linux; alternativa: gateway/ACL; teste parcial na interface |
| Formatos de modelo | Registrados no Ollama (`pull`) ou GGUF + Modelfile importado explicitamente |
| Adaptadores | `http_client_curl`, `port_scanner_nmap` (outros exigem adaptador revisado) |
| Bind mount | UID/GID configuráveis; WSL2 no Windows; ver seção 8 |
| Limites | Seção 11; configuráveis por `.env`, nunca acima da política global |
| Anexos | Markdown (relatório), JSONL (chat/eventos), ZIP com manifesto de hashes; sem PDF |
| Reset | Local: sidecar automatizado; LAN: procedimento humano registrado |

## 16. Estrutura do projeto

```
compose.yaml  compose.pull.yaml  compose.dns-bloqueado.yaml  .env.example
agente/     app.py orchestrator.py discovery.py storage.py reports.py ollama.py config.py   (+ Dockerfile)
proxy/      schemas.py params.py policy.py runner.py
executor/   service.py adapters.py                                                           (+ Dockerfile)
web_ui/     index.html app.js estilo.css nginx.conf                                          (+ Dockerfile)
reset/      reset_service.py                                                                 (+ Dockerfile)
scripts/    init-dados.sh aplicar-egress.sh verificar-egress.sh
dados/      (bind mount; vazio) modelos/{ollama,importar} ferramentas documentacoes __shared__ sessoes banco
exemplos/   ferramentas/*/manifest.json  documentacoes/*.md  modelos/exemplo.Modelfile       (não executáveis)
tests/      test_*.py  fakes/  ui_smoke.py
```
