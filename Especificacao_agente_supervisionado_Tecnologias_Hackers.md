# Roteiro simplificado — ferramenta de agente supervisionado

## Objetivo

Desenvolver uma aplicação web local que integre o Ollama, um modelo escolhido pelo usuário e ferramentas de segurança instaladas na **mesma máquina**. O usuário informa a URL de uma instância autorizada do OWASP Juice Shop na LAN ou inicia uma instância local, define o objetivo e acompanha a investigação. O modelo recebe essa URL, propõe comandos e interpreta resultados; **nenhum comando é executado sem aprovação humana específica**. O usuário pode editar ou rejeitar cada proposta.

O escopo desta entrega é o **software**. O usuário instalará os modelos em seu Ollama e os comandos de segurança no sistema operacional, por exemplo com `apt`; depois escolherá o modelo e listará os comandos que deseja oferecer ao agente. Assume-se que esses recursos estarão disponíveis quando a investigação começar. A aplicação não precisa de Docker, contêineres isolados ou proxy de ferramentas e não baixa modelos ou executáveis por conta própria.

## Arquitetura e arquivos

- **Ollama no host:** fornece a API local de inferência. O usuário instala e gerencia os modelos no próprio Ollama, que mantém seus arquivos no armazenamento configurado pelo usuário. A aplicação consulta a lista de modelos instalados e oferece a seleção de um deles na interface; não importa nem copia pesos.
- **Backend local:** implementado, por exemplo, em Python com FastAPI. Conversa com a API local do Ollama, gerencia sessões, aprovações, catálogo de ferramentas, execução autorizada, logs e exportações.
- **Interface web local:** servida pelo backend em uma porta, por exemplo `127.0.0.1:8080`. O acesso ao Juice Shop na LAN é uma **conexão de saída** iniciada pelos comandos aprovados; não requer uma segunda porta de entrada para a aplicação.
- **Ferramentas no host:** os executáveis são instalados no sistema, fora do projeto, por gerenciadores de pacotes como `apt`. O usuário digita os **nomes dos comandos** que deseja incluir na lista executável, por exemplo `curl` ou `nmap`. O backend resolve cada nome no `PATH` do processo e informa se está disponível; o modelo não recebe acesso ao terminal nem pode alterar a lista.

```text
projeto/
├── app/                       # backend, interface, Ollama, sessões e executor
├── README.md                  # instalação e operação no host
└── dados/                     # apenas configurações e registros persistentes
    ├── catalogo.json          # nomes dos comandos permitidos e descrições
    └── sessoes/<id>/          # planos, chat, logs, evidências e relatório
```

`dados/` não contém modelos, executáveis nem arquivos de documentação: guarda somente as configurações da aplicação e os resultados das sessões. Os modelos persistem no Ollama; os comandos e suas páginas de manual são instalados no sistema. O usuário pode instalar/remover comandos com o gerenciador de pacotes, atualizar a lista permitida e trocar de modelo no Ollama sem reconstruir a aplicação.

## Descoberta e lista de ferramentas

Ao iniciar e sempre que o usuário clicar em **Atualizar recursos**, o backend consulta os modelos instalados no Ollama e verifica **somente os comandos já listados pelo usuário** no `PATH` da aplicação. A interface mostra quando a verificação ocorreu, os modelos disponíveis e quais comandos cadastrados foram encontrados ou deixaram de existir. O sistema não varre todos os binários do computador, não executa comandos durante a verificação e não instala modelos ou ferramentas. A troca de modelo é explícita e não altera silenciosamente uma sessão em curso.

O usuário gerencia uma **lista de comandos que o modelo pode propor**: adiciona ou remove nomes de comandos instalados. O backend confirma se cada nome corresponde a um executável acessível no `PATH`. A documentação é obtida **do sistema**, consultando `man <comando>` e, se necessário, a saída de `<comando> --help`. A consulta ao manual pode ocorrer ao cadastrar/atualizar o comando; executar o próprio comando com `--help` requer aprovação explícita na interface, pois nem todo executável trata essa opção sem efeitos. O resultado é exibido ao usuário e a parte relevante é passada ao modelo, com tamanho limitado. Se nenhuma fonte fornecer instruções úteis, a interface mostra um **aviso**; o usuário continua responsável por decidir se mantém o comando na lista. Comandos indisponíveis ficam sinalizados e não podem ser executados. A cada proposta, o backend resolve novamente o nome e mostra o caminho efetivo para aprovação; antes de executar, confirma que o caminho não mudou, suspendendo a ação se houver alteração. Sessões antigas preservam o nome, caminho e informações usados em cada execução.

Para atender ao enunciado quando o usuário realizar os testes, a lista deverá conter **pelo menos dois comandos/ferramentas**, sendo um capaz de interagir diretamente com o Juice Shop. A plataforma oferece o mecanismo de cadastro, sem distribuir executáveis. Ao propor o uso de uma ferramenta, o modelo recebe as instruções recuperadas de `man` ou `--help` e a indicação da fonte; a sessão registra qual conteúdo de referência foi usado, para permitir reconstruir as decisões mesmo após uma atualização do pacote.

## Interface e execução passo a passo

A tela inicial lista **os modelos instalados no Ollama** para o usuário selecionar um, mostra os comandos cadastrados e sua disponibilidade, o botão **Atualizar recursos** e o campo da **URL do alvo**, por exemplo `http://192.168.1.50:3000/`. O usuário confirma que aquela instância do Juice Shop está autorizada. A opção de iniciar uma instância local pode ser oferecida quando o usuário tiver configurado o Juice Shop no próprio laboratório. O sistema registra a URL escolhida na sessão e a envia ao modelo.

Antes da primeira interação com o modelo, a interface permite registrar **o plano elaborado pelo grupo**: objetivo, hipóteses, estratégia, ferramentas previstas e evidências necessárias. Depois, o modelo pode sugerir alterações, cada uma marcada como aceita, modificada ou rejeitada com justificativa. A interface oferece espaços para **três investigações distintas** e um registro de restauração do Juice Shop a um estado conhecido, com procedimento e confirmação do usuário para o modo local ou LAN.

Para cada passo, o modelo escolhe uma ferramenta da lista e propõe **comando, argumentos e justificativa**. A interface apresenta a linha de comando completa, o destino aparente e os possíveis efeitos, permitindo **Autorizar**, **Editar e autorizar** ou **Rejeitar**. A edição dos argumentos continua vinculada a uma ferramenta cadastrada; trocar o executável exige selecioná-lo explicitamente na lista. Só após a autorização daquela proposta o backend executa o comando; o resultado e eventuais erros retornam ao modelo, que pode propor o passo seguinte conforme as evidências. Rejeições também entram no histórico. O usuário pode interromper o processo a qualquer momento. A aplicação não oferece modo de execução automática ou autorização geral para todos os passos.

O executor local usa o caminho resolvido do comando que ainda pertence à lista do usuário e uma lista de argumentos, sem interpolar a proposta em um shell. Ele aplica tempo máximo, limite de saída e número máximo de ações por sessão, e apresenta novamente o comando final quando o usuário o editar. A URL do alvo e a lista executável orientam a sessão; a interface **avisa** quando um comando parece mencionar outro host ou porta. Sem isolamento de rede ou proxy, a aplicação **não pode garantir tecnicamente** que um executável arbitrário não se conectará a outro destino. A revisão humana de cada comando é, portanto, obrigatória para manter os testes na instância autorizada do Juice Shop.

## Logs, downloads e relatório

Guardar para cada sessão: plano inicial e revisões; modelo escolhido; catálogo/versão das ferramentas utilizadas; fonte e conteúdo da documentação entregue ao modelo; chat completo; URL do alvo; propostas originais e comandos efetivos; decisões e justificativas humanas; horário, saída e erros de cada execução; interpretação posterior do modelo; evidências e conclusões do grupo. Registrar também propostas rejeitadas e comandos que falharam. Cada arquivo produzido recebe identificador, origem e hash para facilitar a conferência.

A interface permite baixar separadamente **o chat**, **os arquivos da sessão**, **os logs e saídas das ferramentas** e **um rascunho editável de relatório**. O relatório organiza as três investigações em hipótese, estratégia, sugestões do modelo, execução, intervenção humana, conclusão e evidências; inclui espaço para comparar o plano humano com as contribuições da IA e apontar pelo menos uma limitação concreta. Campos ainda não preenchidos aparecem como pendentes, sem inventar resultados. O grupo revisará esse rascunho e produzirá posteriormente o relatório acadêmico de **4 a 6 páginas** e o vídeo de até **10 minutos** exigidos pelo enunciado.

## Critérios de aceitação do software

1. A aplicação inicia na máquina do usuário, consulta o Ollama local e lista seus modelos instalados para escolha, inclusive após novas instalações ou remoções.
2. A verificação inicial e a solicitada pela interface atualizam a lista de modelos e conferem a presença dos comandos cadastrados no `PATH`; o usuário pode adicionar ou remover nomes da lista executável.
3. A interface consulta `man <comando>` ou, após aprovação específica, `<comando> --help`, avisa quando não encontra instruções úteis e mostra a URL do Juice Shop e o plano humano antes do uso do modelo.
4. Com duas ferramentas fornecidas pelo usuário, o modelo consegue propor ações diferentes conforme os resultados; cada comando precisa ser autorizado ou editado e autorizado antes da execução.
5. As três investigações e as restaurações do alvo podem ser registradas separadamente; chat, decisões, comandos, resultados e evidências sobrevivem ao reinício da aplicação e podem ser exportados.
6. O rascunho do relatório usa apenas dados efetivamente registrados e destaca as seções ainda pendentes.

**Referência:** enunciado “Avaliação Final — Tecnologias Hackers”. As investigações reais, a restauração da instância do Juice Shop, a análise crítica, o relatório final e o vídeo serão realizados pelo usuário após a entrega da ferramenta.
