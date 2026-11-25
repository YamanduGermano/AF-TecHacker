# Laboratório — Tecnologias Hackers

Aplicação web **local** para investigar uma instância autorizada do OWASP Juice Shop com um modelo do Ollama e ferramentas instaladas no mesmo computador. O modelo analisa, resume e propõe comandos; **você decide**. Nenhum comando é executado sem aprovação humana específica.

## Trabalho Realizado por:

- Yamandu Germano Cavalcanti
- Silas André Pereira de Brito


## Requisitos

- **Python 3.10 ou mais recente** (Linux, macOS ou WSL2)
- **Ollama** instalado e iniciado, com ao menos um modelo
- **Instância autorizada do Juice Shop** - A instância deve ficar a uma máquina acessível para a execução de comandos
- **Ferramentas** instaladas pelo gerenciador de pacotes do sistema, incluindo pelo menos um comando capaz de interagir com o Juice Shop, como `curl`


## Sumário

- [Laboratório — Tecnologias Hackers](#laboratório--tecnologias-hackers)
  - [Trabalho Realizado por:](#trabalho-realizado-por)
  - [Requisitos](#requisitos)
  - [Sumário](#sumário)
  - [Iniciar](#iniciar)
    - [O que você precisa fornecer](#o-que-você-precisa-fornecer)
  - [Primeira sessão](#primeira-sessão)
    - [Navegação](#navegação)
  - [Como a análise funciona](#como-a-análise-funciona)
  - [Comandos manuais](#comandos-manuais)
  - [Skills](#skills)
  - [Plano, restauração e relatório](#plano-restauração-e-relatório)
  - [Aprovação e execução](#aprovação-e-execução)
  - [Arquivos do projeto](#arquivos-do-projeto)
  - [Opções de inicialização](#opções-de-inicialização)
  - [Limitações conhecidas](#limitações-conhecidas)
  - [Solução de problemas](#solução-de-problemas)

## Iniciar

Requisitos: **Python 3.10 ou mais recente** e Linux, macOS ou WSL2 (o executor usa grupos de processos POSIX). Não há dependências Python ou JavaScript para instalar, nem etapa de compilação.

Na pasta do projeto, execute:

```bash
python3 -m app
```

ou `./iniciar.sh`. Abra **http://127.0.0.1:8080** no navegador. Encerre com `Ctrl+C`.

O servidor escuta somente em `127.0.0.1`. O acesso ao Juice Shop na LAN é uma conexão de saída feita pelos comandos aprovados; não é preciso expor a aplicação na rede.

### O que você precisa fornecer

A aplicação não instala nada. Antes de investigar:

1. **Ollama** instalado e iniciado no computador, com ao menos um modelo (instalado pelo próprio Ollama). Modelos pequenos podem ter dificuldade com a resposta JSON estruturada; prefira um que siga bem instruções.
2. **Ferramentas** instaladas pelo gerenciador de pacotes do sistema. Disponibilize pelo menos **dois comandos**, incluindo um capaz de interagir com o Juice Shop, como `curl`.
3. Uma **instância autorizada do Juice Shop**, local ou na LAN. A aplicação não instala, inicia nem reinicia o Juice Shop; as restaurações são registradas manualmente.

## Primeira sessão

1. Abra **Recursos e configurações** (parte inferior da navegação) e clique em **Atualizar**. A aplicação consulta os modelos do Ollama e procura no `PATH` os comandos cadastrados, sem executá-los.
2. Cadastre o **nome** de cada comando (sem caminho ou argumentos) e uma descrição. O backend consulta `man` com limite de 5 s. Se não houver manual, a interface avisa; a consulta a `--help` só ocorre após uma aprovação própria.
3. Clique em **Nova sessão**. Escolha o modelo, informe a URL do alvo, confirme a autorização e preencha o **plano humano** (objetivo, hipóteses, estratégia, ferramentas previstas e evidências necessárias). Os limites de execução ficam recolhidos.
4. Em uma das **três investigações**, clique em **Preparar investigação** e registre hipótese e estratégia. Depois, **Solicitar análise**.
5. A síntese aparece no painel principal; a proposta de comando, ao lado. Confira a linha completa, o caminho efetivo, os destinos aparentes e os possíveis efeitos.
6. **Revisar e autorizar** abre a confirmação daquela execução. **Editar** permite trocar o comando (entre os cadastrados) e os argumentos, e apresenta o comando final para nova aprovação. **Rejeitar** preserva a proposta com sua justificativa.

O modelo e o alvo ficam fixos na sessão; para trocá-los, crie outra sessão. **Atualizar recursos** não altera o modelo de uma sessão existente.

### Navegação

| Aba | Conteúdo |
|---|---|
| **Explorações** | As três investigações: síntese, memória, proposta pendente, skills e anotações do grupo. |
| **Chat** | Conversa com o modelo e fluxo de execuções. Use para orientar a análise. |
| **Atividade** | Decisões, erros, avisos, saídas e arquivos registrados, com visualização do conteúdo. |
| **Relatório** | Comparação plano humano × IA, limitações, revisões do plano, restaurações e exportações. |

Qualquer aba (e cada painel) pode ser ampliada pelo botão junto ao título. `Esc` restaura.

## Como a análise funciona

Cada **Solicitar análise** envia ao Ollama um contexto montado pelo backend e recebe uma resposta JSON **validada por esquema**. Ela contém: resumo de progresso, síntese, observações, limitações, próxima questão, memória consolidada e, opcionalmente, uma proposta de comando, pedido de skill, pedido de releitura de evidência ou sugestão de revisão do plano.

- **Respostas em streaming.** O resumo de progresso, a síntese e a justificativa aparecem enquanto o modelo escreve. Só o conteúdo público é usado; campos de raciocínio privado são ignorados.
- **Ciclo supervisionado.** Após uma execução autorizada, o backend devolve o resultado ao modelo, que o interpreta e pode propor outro passo. **Esse novo passo nunca é executado automaticamente.**
- **Memória por investigação.** O modelo mantém um resumo *consolidado* (conclusões, perguntas em aberto, próximos passos), não uma transcrição. Cada conclusão referencia IDs de evidências reais; referências inexistentes ou de outra investigação são removidas e geram aviso. A memória é conteúdo gerado pelo modelo: não prova nada por si. Versões anteriores ficam no histórico da sessão.
- **Histórico de tentativas.** O modelo vê as últimas tentativas (comando, estado, código de saída, decisão humana, edições). Repetir um comando já executado ou rejeitado exige `retry_reason`; a repetição gera um **aviso para revisão humana**, sem bloquear a proposta.
- **Releitura de evidências.** O modelo pode pedir até dois IDs de evidências da investigação. O backend devolve trechos verificados por SHA-256, sem executar comandos. Há no máximo uma rodada de leitura por análise; arquivos binários ou com hash divergente não são fornecidos.
- **Contexto limitado.** O prompt é compactado para caber em 14.000 caracteres (janela de 8192 tokens, resposta de até 3072). Mensagens longas, documentação e saídas são abreviadas por prioridade: pedido atual, memória e último resultado são mantidos por último. O contexto **exato** enviado é salvo como evidência a cada rodada, e o histórico completo permanece em disco.
- **Intervenção humana visível.** Quando você edita um comando, o modelo é informado de que o comando efetivo difere da proposta original.
- **Respostas inválidas.** JSON inválido, proposta rejeitada pelo validador (ferramenta não cadastrada, argumentos fora do formato) ou falha do Ollama ficam registrados em Atividade; a resposta original permanece no Chat e nenhum comando é criado.

## Comandos manuais

O botão **Executar comando** (no topo, com uma sessão aberta) permite que **você** defina um comando entre os cadastrados:

1. Informe a ferramenta, a linha de comando e, opcionalmente, uma nota.
2. A **prévia** mostra o comando final e o caminho resolvido.
3. Confirme para executar. A execução passa pelo mesmo executor auditado das propostas do modelo, com os mesmos limites.
4. Marque a opção de **analisar o resultado ao terminar** se quiser que o modelo interprete o resultado; do contrário a sessão volta a ficar pronta sem consultar o modelo.

Esses comandos têm `origin=manual`: o modelo os trata como evidência real, mas não como ação sua. Repetições da mesma requisição HTTP nunca iniciam um segundo processo.

## Skills

Skills são **guias de interpretação em Markdown** (texto), não scripts: não executam nada nem concedem permissões. Ficam na pasta [skills/](skills/) do projeto, com o catálogo em `skills/skills.json`.

Incluídas por padrão (cópias em `app/default_skills/` são restauradas se faltarem):

- `interpretar-saidas`, `interpretar-http`, `interpretar-json`: leitura de saídas de comandos, respostas HTTP e JSON;
- notas das aulas: Sistemas operacionais; Comunicação de dados e análise de logs; Coleta de informações e Nmap; Reconhecendo o alvo, gestão e nuvem; Técnicas de reconhecimento web; Credenciais e armazenamento de senhas; LFI, RFI e inclusão de arquivos; Questões de revisão comentadas.

Uso:

- **Por sessão:** ative ou desative skills da sessão. O modelo também pode pedir até duas skills do catálogo (`skill_requests`), a menos que você as tenha desativado naquela sessão.
- **Importar:** cole ou envie um arquivo `.md`/`.txt` de até **2400 caracteres**; o catálogo aceita até 20 skills.
- **Limites ativos:** 3 skills e 4800 caracteres de instruções por sessão.
- **Edição:** o arquivo `.md` é relido antes de cada inferência. Se mudou, a nova versão é registrada como evidência. Se um arquivo ficar indisponível ou exceder os limites, a análise é recusada até você corrigi-lo ou desativar a skill.
- **Rastreabilidade:** cada skill ativada é salva na sessão com SHA-256, e cada síntese registra quais skills estavam no contexto.

O modelo é instruído a tratar skills como subordinadas às regras de autorização, evidência e formato; isso reduz, mas não elimina, o risco de uma skill mal escrita influenciar a análise.

## Plano, restauração e relatório

- O **plano inicial é preservado**. O modelo pode sugerir revisões em qualquer campo; cada sugestão pode ser **aceita, modificada ou rejeitada**, sempre com justificativa humana.
- Cada investigação tem hipótese, estratégia, sínteses, conclusão do grupo e evidências.
- **Registrar restauração** guarda procedimento, modo (local/LAN), investigação e a confirmação do estado conhecido. É um registro do que o grupo fez; nada é executado. O modelo recebe a última restauração e é instruído a explicitar o que precisa ser revalidado.
- **Relatório** reúne a comparação entre plano humano e contribuições da IA e as limitações concretas.
- **Exportar** gera chat (JSON), logs/saídas (JSON), rascunho em Markdown e pacote ZIP completo. Há **prévia** na interface antes do download.
- O rascunho usa só os registros existentes e marca lacunas como **PENDENTE**. O grupo ainda deve produzir o relatório acadêmico de 4 a 6 páginas e o vídeo de até 10 minutos.

## Aprovação e execução

O modelo não recebe terminal. Propostas são dados estruturados: **comando cadastrado + lista de argumentos**. A execução usa `subprocess.Popen(..., shell=False)` com stdin fechado, em um diretório de trabalho próprio por comando.

Antes da aprovação, o backend resolve o comando no `PATH` e registra caminho real, SHA-256, tamanho e data de modificação. Antes de executar, confere de novo o cadastro e a identidade do arquivo. Se algo mudou, a ação é **suspensa**; autorizações antigas não são reutilizadas, e aprovações repetidas são recusadas. A proposta só é aprovada se a revisão exibida for a vigente.

Limites padrão por sessão (ajustáveis ao criar a sessão):

| Limite | Padrão | Faixa |
|---|---:|---:|
| Tempo por comando | 30 s | 1–300 s |
| stdout + stderr | 128 KiB | 1 KiB–1 MiB |
| Ações autorizadas | 30 | 1–100 |

O executor encerra o grupo de processos ao interromper, exceder tempo ou saída, ou terminar; não depende de o comando manter os pipes abertos. Processos deliberadamente desvinculados do grupo não são contidos.

**Interromper** cancela o comando ou a inferência em curso e impede novas propostas. Uma resposta tardia do modelo é arquivada como descartada, sem gerar propostas. O Ollama tem limite de 180 s por resposta.

**Segurança da interface.** O backend usa token por execução, verificação de `Host` e `Origin`, recusa chamadas entre sites, limita o corpo das requisições a 100 KB e envia CSP restritiva. Conteúdo do modelo e das ferramentas é exibido como texto, sem interpretar HTML, e saídas e documentos são tratados como dados não confiáveis no prompt. Isso não substitui isolamento de sistema nem autenticação multiusuário.

**Avisos de destino são heurísticos.** Hosts, URLs e portas nos argumentos que diferem do alvo geram alertas, mas **não há isolamento de rede ou de sistema de arquivos**: um executável pode seguir redirecionamentos, usar configurações próprias, acessar outros destinos ou alterar arquivos. Por isso a revisão humana de cada linha é obrigatória. Não execute a aplicação como root e não exponha a porta por túnel ou proxy.

## Arquivos do projeto

```text
.
├── app/
│   ├── __main__.py       # inicialização e encerramento
│   ├── server.py         # HTTP local, rotas e verificações de origem/token
│   ├── service.py        # sessões, propostas, decisões e fluxo supervisionado
│   ├── agent.py          # prompt, esquema JSON da resposta e streaming público
│   ├── memory.py         # memória consolidada, histórico, evidências e compactação do contexto
│   ├── skills.py         # catálogo global de skills em Markdown
│   ├── resources.py      # Ollama, PATH, man e validação de alvo
│   ├── executor.py       # subprocessos e limites
│   ├── storage.py        # JSON persistente e arquivos com hash
│   ├── reports.py        # rascunho e exportações
│   ├── default_skills/   # skills incluídas (restauradas se faltarem)
│   └── static/           # HTML, CSS e JavaScript sem frameworks
├── skills/               # skills ativas no catálogo (Markdown + skills.json)
├── dados/
│   ├── catalogo.json     # comandos cadastrados
│   ├── consultas.json    # consultas --help autorizadas
│   └── sessoes/<id>/
│       ├── sessao.json
│       ├── arquivos/     # evidências: saídas, contextos enviados ao modelo, skills, exportações
│       └── execucoes/    # diretório de trabalho por comando
├── Especificacao_agente_supervisionado_Tecnologias_Hackers.md
├── Resumo_Tecnologias_Hackers.md   # guia de estudo da disciplina
├── Arquitetura.pdf
├── iniciar.sh
└── README.md
```

`dados/` contém somente configuração e registros, nunca modelos ou executáveis. Para backup, copie-o com a aplicação encerrada. Não inicie dois servidores sobre o mesmo diretório.

**Persistência.** Escritas JSON são atômicas. As sessões preservam mensagens, o contexto exato enviado ao modelo, plano inicial e revisões, propostas originais, edições, decisões, resultados, memória (com histórico) e restaurações. Ao reiniciar, ações em curso ficam marcadas como interrompidas, sem retomada automática.

**Evidências.** Cada arquivo recebe ID, origem e SHA-256. A saída de cada comando é registrada em JSON mesmo quando ele falha. Arquivos regulares criados no diretório de trabalho do comando são incorporados até **20 MiB / 49 arquivos por execução**; links simbólicos são ignorados e arquivos fora desse diretório não são descobertos. O limite não impede um executável de gravar arquivos grandes no computador. Cada download de exportação envia `X-Content-SHA256` e `X-Lab-Artifact-ID`; o ZIP inclui `manifesto.json` e não aninha ZIPs anteriores.

> **Atenção ao versionar.** `dados/sessoes/` guarda alvos, saídas de comandos e o contexto enviado ao modelo. A linha correspondente do `.gitignore` está comentada, então sessões podem ser commitadas por engano. Revise o que vai para o repositório. O `.env.example` lista variáveis (`PLATAFORMA_UID`, `PLATAFORMA_GID`, `EXECUTOR_TOKEN`, `RESET_TOKEN`) que o código atual **não lê**.

## Opções de inicialização

```bash
python3 -m app --port 8081
python3 -m app --data-dir /caminho/para/dados
python3 -m app --ollama-url http://127.0.0.1:11434
```

O endereço do Ollama aceita apenas HTTP em loopback, sem caminho ou credenciais. Proxies do ambiente não são usados nessas chamadas. A aplicação usa `GET /api/tags` e `POST /api/chat` (em streaming, com `format` por esquema JSON). Referência: [API do Ollama](https://docs.ollama.com/api). A pasta de skills é sempre `skills/` na raiz do projeto.

## Limitações conhecidas

- **Não há testes automatizados no repositório** e a ferramenta **não foi validada contra uma instância real do Juice Shop** neste README. O registro de uma sessão de teste está em `dados/sessoes/`; nela, as duas execuções registraram estado *failed*. Revise a Atividade antes de tirar conclusões.
- A qualidade das propostas depende do modelo escolhido. Modelos pequenos podem produzir JSON inválido, propostas repetidas ou conclusões sem suporte; a memória e as sínteses são hipóteses a conferir nas evidências, não resultados verificados.
- O contexto compactado pode omitir detalhes de saídas longas. O histórico completo continua salvo e acessível em Atividade.
- Não há isolamento de rede ou de arquivos (veja [Aprovação e execução](#aprovação-e-execução)).
- Uma sessão só é retomada em estado pausado após reinício; execuções e inferências interrompidas não continuam sozinhas.

## Solução de problemas

- **Ollama não conectado:** confira se o serviço está iniciado na mesma máquina e use **Atualizar recursos**. No WSL2, mantenha aplicação, Ollama e ferramentas na mesma distribuição.
- **Modelo indisponível:** instale-o pelo Ollama e atualize a lista. A aplicação não troca de modelo silenciosamente.
- **Comando não encontrado:** confirme que está no `PATH` do processo que iniciou a aplicação e cadastre apenas o nome.
- **Manual ausente:** instale o pacote de documentação do sistema ou autorize `--help`. O aviso não impede manter o comando.
- **"Cadastre pelo menos dois comandos disponíveis":** a análise só começa com dois comandos resolvidos no `PATH`.
- **Proposta suspensa:** o executável mudou; revise o ambiente e solicite nova análise.
- **Proposta recusada pelo validador:** o modelo propôs algo fora do formato (por exemplo, ferramenta não cadastrada). O motivo está em Atividade; peça nova análise ou oriente no Chat.
- **JSON inválido do modelo:** a resposta original está no Chat. Solicite outra análise ou crie uma sessão com um modelo que siga instruções JSON.
- **"Contexto compacto excedeu o limite":** reduza o pedido atual ou as anotações do grupo.
- **Skill indisponível ou acima do limite:** corrija o Markdown em `skills/` ou desative a skill na sessão.
- **Token inválido após reiniciar:** recarregue a página.
- **Porta ocupada:** use `--port`.
- **Saída interrompida:** veja Atividade; a razão distingue tempo, limite de saída, interrupção e erro.
