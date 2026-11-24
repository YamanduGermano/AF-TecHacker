# Laboratório — Tecnologias Hackers

Aplicação web **local** para investigar uma instância autorizada do OWASP Juice Shop com Ollama e ferramentas instaladas no mesmo computador. A interface prioriza as sínteses e as três investigações. Cada comando precisa de aprovação humana específica.

## Iniciar

Requisitos: **Python 3.11 ou mais recente**, Linux, macOS ou WSL2. Não há dependências Python ou JavaScript para instalar, nem etapa de compilação.

Extraia o ZIP, entre na pasta `laboratorio` e execute:

```bash
python3 -m app
```

Abra **http://127.0.0.1:8080** no navegador. Encerre com `Ctrl+C`.

Alternativamente, execute `./iniciar.sh`.

O backend escuta somente em `127.0.0.1`. O acesso ao Juice Shop na LAN é uma conexão de saída; não é preciso expor a aplicação na rede.

### Recursos fornecidos pelo usuário

Antes de investigar:

1. Instale e inicie o Ollama no computador. Instale o modelo que preferir usando o próprio Ollama.
2. Instale as ferramentas pelo gerenciador de pacotes do sistema. A aplicação não instala nada. Para cumprir o enunciado, disponibilize pelo menos **dois comandos**, incluindo um capaz de interagir com o Juice Shop, como `curl`.
3. Disponibilize uma instância autorizada do Juice Shop, localmente ou na LAN. Esta versão registra restaurações manuais; não instala, inicia nem reinicia o Juice Shop.

## Primeira sessão

1. Abra **Recursos e configurações** na parte inferior da navegação.
2. Clique em **Atualizar** para consultar os modelos e verificar os comandos cadastrados. A checagem consulta o `PATH`, sem executar os comandos ou varrer todos os binários.
3. Cadastre os nomes dos comandos e uma descrição. O backend consulta `man` com limite de tempo. O manual, quando disponível, aparece em detalhes. Se não houver instruções úteis, a interface avisa; a consulta a `--help` só acontece após uma aprovação própria.
4. Clique em **Nova sessão**. Escolha o modelo instalado, a URL do alvo e confirme a autorização. Registre objetivo, hipóteses, estratégia, ferramentas previstas e evidências necessárias. Limites menos frequentes ficam recolhidos.
5. Em uma das três investigações, clique em **Preparar investigação** e registre a hipótese e a estratégia. Depois, selecione **Solicitar análise**. O início da análise exige dois comandos disponíveis.
6. A síntese aparece no painel principal. A proposta de comando aparece ao lado. Confira a linha completa, o caminho efetivo, os destinos aparentes e os possíveis efeitos.
7. **Revisar e autorizar** abre a confirmação daquela execução. **Editar** permite escolher explicitamente outro comando cadastrado e alterar a lista de argumentos em JSON; depois apresenta o comando final para nova aprovação. **Rejeitar** exige justificativa e preserva a proposta.
8. Após uma execução autorizada, o backend entrega o resultado ao Ollama. O modelo pode interpretar a saída e propor outro passo. **Esse novo passo nunca é executado automaticamente.**

Use **Chat** para orientar o modelo. As sínteses continuam organizadas nas **Explorações**. **Atividade** mostra decisões, erros, saídas e detalhes completos. Qualquer aba pode ser ampliada pelo botão junto ao título; cada painel também tem seu próprio botão de maximização. `Esc` restaura o painel.

As configurações só aparecem quando solicitadas. O modelo e o alvo ficam fixos na sessão; para trocá-los, crie outra sessão. **Atualizar recursos** não troca o modelo de uma sessão existente.

## Plano, restauração e relatório

- O plano inicial é preservado. Sugestões do modelo podem ser aceitas, modificadas ou rejeitadas, sempre com justificativa humana.
- Cada investigação possui hipótese, estratégia, sínteses, conclusão do grupo e referências às evidências.
- **Registrar restauração** guarda procedimento, modo local/LAN, investigação e confirmação do estado conhecido. É um registro do que o grupo já fez, sem execução automática.
- **Relatório** permite escrever a comparação entre plano humano e contribuições da IA, além das limitações concretas.
- **Exportar** oferece chat JSON, logs/saídas JSON, pacote ZIP completo e rascunho editável Markdown.
- O rascunho usa somente os registros existentes e marca lacunas como **PENDENTE**. O grupo ainda deve revisar e produzir o relatório acadêmico de 4 a 6 páginas e o vídeo de até 10 minutos.

## Aprovação e execução

O backend não entrega um terminal ao modelo. Propostas são dados estruturados: comando cadastrado + lista de argumentos. A execução usa `subprocess.Popen(..., shell=False)`, com stdin fechado.

Antes da aprovação, o backend resolve o comando no `PATH`, registra o caminho real, SHA-256, tamanho e data de modificação. Antes de executar, verifica novamente o cadastro e a identidade do arquivo. Uma alteração suspende a ação; autorizações antigas não são reutilizadas. Requisições repetidas de aprovação também são recusadas.

Valores padrão por sessão:

| Limite | Padrão | Faixa configurável ao criar sessão |
|---|---:|---:|
| Tempo por comando | 30 segundos | 1–300 segundos |
| stdout + stderr | 128 KiB | 1 KiB–1 MiB |
| Ações autorizadas | 30 | 1–100 |

O executor encerra o grupo de processos ao interromper, exceder tempo/saída ou terminar. Não depende de o comando manter seus pipes abertos. Processos deliberadamente desvinculados do grupo não são isolados por esta aplicação.

**Interromper** cancela o comando em andamento e impede novas propostas automáticas. Durante inferência, uma resposta tardia é arquivada, mas não gera propostas. A conexão com Ollama pode levar até 180 segundos para encerrar; a sessão aguarda seu encerramento antes de aceitar outra análise.

Os alertas de host/porta são heurísticos. **Não há isolamento de rede ou sistema de arquivos.** Um executável pode seguir redirecionamentos, usar configurações próprias, acessar outros destinos ou alterar arquivos. Por isso a revisão humana de cada linha é obrigatória. Não execute a aplicação como root e não exponha sua porta por túnel ou proxy.

Requisições da interface usam token por execução da aplicação, verificação de Host/origem e recusa de chamadas entre sites. Conteúdo do modelo e de ferramentas é exibido como texto, sem interpretar HTML. Essas medidas não substituem isolamento de sistema ou autenticação para múltiplos usuários.

## Arquivos do projeto

```text
laboratorio/
├── app/
│   ├── __main__.py       # inicialização e encerramento
│   ├── server.py         # HTTP local e rotas
│   ├── service.py        # sessões, propostas, decisões e fluxo supervisionado
│   ├── resources.py      # Ollama, PATH e referências do sistema
│   ├── agent.py          # contexto e resposta estruturada do modelo
│   ├── executor.py       # subprocessos e limites
│   ├── storage.py        # JSON persistente e arquivos com hash
│   ├── reports.py        # rascunho e exportações
│   └── static/           # HTML, CSS e JavaScript sem frameworks
├── tests/
├── dados/
│   ├── catalogo.json
│   ├── consultas.json   # criado ao consultar --help
│   └── sessoes/<id>/
│       ├── sessao.json
│       ├── arquivos/    # cópias registradas, contextos e saídas
│       └── execucoes/   # diretório de trabalho por comando
├── iniciar.sh
└── README.md
```

O diretório `dados/` contém somente configuração e registros, nunca modelos ou executáveis. Faça uma cópia dele, com a aplicação encerrada, para backup. Não inicie dois servidores apontando para o mesmo diretório. Os testes usam diretórios temporários e não alteram seus registros.

Sessões preservam mensagens, contexto exato enviado ao modelo, referências de documentação utilizadas, plano inicial, revisões, propostas originais, edições, decisões, resultados e restaurações. Escritas JSON são substituídas atomicamente. Ao reiniciar, ações em curso ficam marcadas como interrompidas, sem retomada automática.

Arquivos incorporados recebem ID, origem e SHA-256. As saídas JSON são registradas mesmo quando o comando falha. Arquivos regulares produzidos no diretório de trabalho são incorporados até **20 MiB / 49 arquivos por execução**; links simbólicos são ignorados. Arquivos escritos fora desse diretório não são descobertos automaticamente. O limite não impede um executável de criar arquivos grandes no computador.

Cada exportação também é registrada com hash e ID; os downloads enviam esses valores nos cabeçalhos `X-Content-SHA256` e `X-Lab-Artifact-ID`. O ZIP inclui `manifesto.json` para conferir os arquivos internos. ZIPs anteriores não são incluídos recursivamente em novos pacotes.

O contexto do modelo é limitado: até 20 mensagens recentes da investigação, dez propostas recentes, trechos de saída e trechos da documentação. O histórico completo permanece salvo e exportável. O modelo recebe as fontes dos trechos; documentação ausente continua explicitamente sinalizada.

## Opções de inicialização

```bash
python3 -m app --port 8081
python3 -m app --data-dir /caminho/para/dados
python3 -m app --ollama-url http://127.0.0.1:11434
```

O endereço do Ollama aceita apenas loopback. Proxies configurados no ambiente não são usados nas chamadas ao Ollama. A aplicação usa `GET /api/tags` e `POST /api/chat`, sem streaming, com resposta JSON. Referência: [API do Ollama](https://docs.ollama.com/api).

## Validação

```bash
python3 -m unittest discover -s tests -v
```

Opcionalmente, com Node 18+ instalado, `node tests/ui_smoke.cjs` verifica a geração das quatro abas, estados vazios/preenchidos e o escape de conteúdo. Node não é necessário para usar a aplicação.

A suíte cobre: limites de tempo/saída, interrupção, fechamento antecipado dos pipes, comandos com erro, argumentos literais sem shell, aprovação específica e não reutilizável, revisão de comandos, mudança do executável, remoção de ferramenta, limite de ações, fluxo adaptativo com Ollama simulado, JSON inválido do modelo, resposta tardia após interrupção, atualização de recursos sem execução, aprovação de `--help`, três investigações, restauração, revisão do plano, persistência, exportação e hashes, Host/origem/token e rotas HTTP.

Os testes usam executáveis temporários inofensivos e respostas simuladas do Ollama. **Não foram realizados testes reais contra Juice Shop nem inferência com um modelo instalado.** O ambiente de entrega não disponibilizou a prévia de navegador; o HTML/JS e o backend foram verificados sem validação visual automatizada.

## Solução de problemas

- **Ollama não conectado:** confira se o serviço está iniciado na mesma máquina e use Atualizar recursos. No WSL2, mantenha a aplicação, o Ollama e as ferramentas na mesma distribuição, conforme a arquitetura proposta.
- **Modelo indisponível:** instale-o pelo Ollama e atualize a lista. A aplicação não troca para outro modelo silenciosamente.
- **Comando não encontrado:** confirme que ele está no `PATH` do processo que iniciou a aplicação. Cadastre apenas o nome, sem caminhos ou argumentos.
- **Manual ausente:** instale o pacote de documentação pelo sistema ou autorize `--help`. Um aviso não impede manter o comando cadastrado.
- **Proposta suspensa:** o executável mudou; revise o ambiente e solicite outra análise.
- **JSON inválido do modelo:** a resposta original está no Chat. Solicite outra análise ou crie uma sessão com um modelo que siga instruções JSON.
- **Token inválido após reiniciar:** recarregue a página.
- **Porta ocupada:** escolha outra com `--port`.
- **Saída interrompida:** consulte Atividade; a razão distingue tempo, limite de saída, interrupção e erro.
