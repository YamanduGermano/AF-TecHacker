# especificação_do_projeto.md

## 1. Objetivo e escopo

Desenvolver **a plataforma**, no kit de laboratório da disciplina, para integrar um modelo local e ferramentas de segurança fornecidos posteriormente pelo usuário. A plataforma apoiará investigações sobre **uma instância autorizada do OWASP Juice Shop**. O usuário poderá iniciar uma instância local opcional ou informar a URL de uma instância já disponível em um computador da LAN do laboratório. O agente recebe o objetivo e a URL definida pelo usuário, interpreta observações, escolhe entre ferramentas cadastradas, propõe ações e interpreta resultados. **Cada execução depende de autorização humana**, com possibilidade de editar ou rejeitar a proposta. O sistema registra todas as etapas, inclusive decisões negativas, para permitir análise técnica e crítica posterior.

O escopo desta especificação é **desenvolver o software**, não baixar, incluir ou entregar pesos de modelos, executáveis de teste, documentação dessas ferramentas, resultados de investigações, relatório acadêmico final ou vídeo. O usuário fornecerá os recursos e conduzirá as investigações posteriormente. A plataforma oferece os controles e registros necessários para examinar quando a IA ajudou ou errou; uma afirmação do modelo não constitui evidência de vulnerabilidade.

## 2. Arquitetura proposta

Usar Docker Compose para iniciar quatro serviços da plataforma e, opcionalmente, um quinto serviço para o alvo local:

| Serviço | Responsabilidade | Acesso |
| --- | --- | --- |
| `juice-shop` (opcional) | Instância local e restaurável do alvo, ativada quando o usuário não aponta para o Juice Shop da LAN | Rede do laboratório; publicação local opcional para acesso do Kali |
| `ollama` | Servidor local de inferência; inicialmente sem modelo instalado | Apenas API interna acessível pelo orquestrador; armazenamento montado no volume persistente |
| `agente` | Backend, controle de sessões, integração com o modelo, aprovação humana, proxy de ferramentas e armazenamento | Redes internas necessárias; nunca oferece shell ao modelo |
| `executor` | Executa somente ferramentas habilitadas por chamadas do proxy, com recursos e rede restritos | Lê a árvore de ferramentas montada sem permissão de escrita e usa área de resultados separada; não recebe os diretórios de modelos ou banco de sessões |
| `web-ui` | Chat, ações pendentes, plano, evidências, configuração do alvo e exportação | Porta da interface publicada apenas no host do laboratório |

O proxy pode ser um módulo Python do serviço `agente`, sem porta pública adicional. O backend recebe uma **proposta estruturada** do modelo, valida o formato, solicita aprovação, valida de novo os parâmetros aprovados e só então chama o `executor` por uma API interna restrita. A execução gera um resultado registrado, que volta ao histórico do modelo. O fluxo pode ser implementado com FastAPI e uma interface web simples; SQLite guarda sessões e metadados, enquanto arquivos imutáveis por execução guardam resultados brutos. A imagem da plataforma inclui apenas o código e suas dependências genéricas; o primeiro acesso funciona sem modelo ou ferramentas instalados e orienta o usuário a adicioná-los.

**Portas:** a porta publicada da interface, por exemplo `127.0.0.1:8080`, é a entrada do usuário. Quando a instância opcional do Juice Shop for iniciada localmente, sua porta, por exemplo `3000`, pode ser publicada para acesso do Kali; na modalidade com alvo já existente na LAN, **nenhuma segunda porta de entrada no Docker é necessária**. O `executor` inicia conexões de saída para a URL informada pelo usuário, ou para `juice-shop:3000` no modo local. As APIs do Ollama, proxy e executor não são publicadas. A conectividade de saída do executor deve permitir alcançar o computador da LAN que hospeda o alvo, enquanto sua política bloqueia os demais destinos. Se o Kali estiver em outra VM, documentar o encaminhamento ou a rede do laboratório aplicável a cada modo.

## 3. Estrutura dos arquivos

```text
projeto/
├── compose.yaml
├── .env.example
├── README.md
├── proxy/
│   ├── policy.py                 # escopo, validação, limites
│   ├── runner.py                 # pedido controlado ao executor
│   └── schemas.py                # entradas e saídas estruturadas
├── executor/
│   ├── service.py                # API interna para execução autorizada
│   └── adapters.py               # perfis de ferramentas aceitos
├── agente/
│   ├── app.py                    # API, sessões e aprovações
│   ├── orchestrator.py           # ciclo modelo → revisão → ferramenta
│   ├── discovery.py              # varredura, validação e catálogo
│   ├── storage.py                # logs e evidências
│   └── reports.py                # rascunho do relatório
├── web_ui/
│   └── ...                       # página web, estilos e JavaScript
└── dados/                        # bind mount persistente, acessível no host
    ├── modelos/
    │   ├── ollama/               # armazenamento de modelos registrados
    │   └── importar/             # arquivos locais a validar/importar
    ├── ferramentas/<id>/
    │   ├── manifest.json         # definição do contrato e política
    │   └── executavel            # fornecido pelo usuário
    ├── documentacoes/<id>.md     # fornecidas pelo usuário
    ├── __shared__/               # entrada provisória de recursos adicionais
    └── sessoes/<id>/
        ├── plano-inicial.md
        ├── eventos.jsonl
        ├── chat.jsonl
        ├── evidencias/
        ├── resultados-ferramentas/
        └── relatorio.md
```

`dados/` é um **diretório do host montado nos contêineres**, com instruções de permissões e caminhos no README. Assim, o usuário vê seus modelos e arquivos, pode adicionar ou remover recursos e preserva o conteúdo ao recriar os contêineres. O armazenamento do Ollama é configurado para `dados/modelos/ollama/`; não colocar uma segunda cópia de pesos na imagem. `dados/modelos/importar/` recebe apenas formatos de importação explicitamente suportados (por exemplo, GGUF acompanhado de definição de importação); copiar um arquivo ali não o transforma automaticamente em um modelo carregável. O usuário também pode registrar modelos pelos comandos locais do Ollama usando o mesmo armazenamento persistente. `__shared__/` é uma área de entrada, não um diretório automaticamente executável. `dados/sessoes/` armazena os registros; recursos sensíveis não devem ser publicados em repositórios abertos.

## 4. Descoberta, atualização e seleção de recursos

Na inicialização do backend e ao clicar em **Verificar novos recursos**, executar uma varredura dos diretórios persistentes. O botão aciona um endpoint do backend e mostra horário, andamento, recursos novos, alterados, removidos, erros de validação e status final; a mesma operação deve poder ser chamada pela API. O catálogo é reconstruído a partir do estado real do volume e da lista de modelos registrados no Ollama, de forma repetível, sem depender de reiniciar os contêineres. Recursos removidos desaparecem das opções para novas sessões, mas seu histórico continua nos registros.

Para **modelos**, enumerar modelos registrados e arquivos candidatos em `dados/modelos/importar/`. Validar formato/definição, mostrar os candidatos como **pendentes de importação** e apenas disponibilizar para seleção os modelos efetivamente registrados e acessíveis pela API local. Importação ou troca do modelo ativo requer uma ação explícita do usuário. A interface apresenta nome, versão/tag, estado e eventual erro; selecionar outro modelo altera **novas sessões** ou exige confirmação para reiniciar o contexto de uma sessão existente. Guardar no log o identificador e a versão do modelo usados em cada interação. A varredura não baixa modelos da internet nem presume que qualquer arquivo colocado no diretório seja compatível com o Ollama.

Para **ferramentas**, identificar entradas de `dados/ferramentas/<id>/` e, se desejado, candidatos de `dados/__shared__/`. Verificar manifesto legível, ID único, executável existente, permissões, formato aceito, esquema de parâmetros, limites e documentação associada em `dados/documentacoes/`. Mostrar separadamente **detectada**, **inválida**, **sem documentação**, **pendente de habilitação** e **habilitada**; uma ferramenta nova ou alterada não é executada na varredura nem é habilitada por si só. Mostrar o aviso de documentação ausente mesmo quando a ferramenta estiver desabilitada. Para habilitar, o usuário revisa o manifesto e a política aplicável; em nenhuma hipótese o manifesto pode pedir shell livre, destino alternativo ou permissões fora da política global. A documentação presente será disponibilizada ao modelo; a ausente impede sua utilização até ser adicionada e revisada.

Para evitar alterações durante uma execução, registrar hash/versão do manifesto, documentação, executável e modelo escolhidos. Revalidar a identidade do executável imediatamente antes do uso; se mudou, suspender a proposta e exigir nova revisão. Sessões existentes conservam o histórico dos recursos anteriores e não migram silenciosamente para uma versão diferente. A varredura apenas **descobre e valida**; executar, importar, habilitar e alterar uma sessão são operações distintas e explícitas.

## 5. Interface e fluxo da sessão

Na tela inicial, o usuário escolhe **Iniciar Juice Shop local** ou **Usar Juice Shop da LAN**. Na segunda opção, informa uma URL completa, por exemplo `http://192.168.1.50:3000/`, e confirma que é uma instância autorizada para os testes. A interface apresenta a URL normalizada, o endereço resolvido, a porta, o status de conectividade e o escopo fixado para a sessão. Exibe também o **modelo selecionado**, o estado das ferramentas e o botão **Verificar novos recursos**. Sem um modelo registrado ou sem ferramentas habilitadas, a interface permanece acessível para configuração e explica o que falta para iniciar uma investigação. O usuário define nome da sessão e objetivo; e preenche **antes de consultar o modelo** um plano com aspectos da aplicação, hipóteses iniciais, estratégia, ferramentas e evidências esperadas. O plano é salvo com data e versão. **Depois disso, o modelo selecionado recebe a URL escolhida e o objetivo como contexto da sessão** e pode revisar o plano; cada sugestão fica marcada como aceita, alterada ou rejeitada com justificativa técnica.

Na tela principal, exibir:

1. Chat da sessão, separado visualmente de mensagens de sistema, propostas de ferramenta, saídas e interpretações.
2. Catálogos de modelos e ferramentas encontrados na varredura, com seleção do modelo, botão de nova varredura, finalidade e limites das ferramentas, status de validação e aviso visível de documentação ausente. Ferramenta sem documentação ou cadastro válido fica indisponível para propostas do agente até correção e revisão humana.
3. Cartão de **ação pendente** com ferramenta, parâmetros normalizados, URL/porta efetiva, justificativa do modelo e botões **Autorizar**, **Editar e autorizar** e **Rejeitar**, todos com campo de justificativa para modificações ou rejeições. A aprovação se aplica somente àquela proposta; não existe aprovação geral da sessão.
4. Linha do tempo com ações, respostas, evidências e decisões posteriores do grupo, agrupadas por investigação.
5. Exportação independente do chat, dos arquivos da sessão, dos resultados brutos das ferramentas e de um relatório técnico gerado como **rascunho editável**; arquivos grandes podem ser entregues em ZIP com manifesto e hashes.
6. Controles para iniciar uma das três investigações e restaurar o Juice Shop a um estado conhecido: reset automatizado quando o alvo for o contêiner local, ou registro de procedimento e confirmação humana quando o alvo estiver em outro computador da LAN.

O ciclo de cada proposta é: **objetivo → resposta do modelo em JSON validado → apresentação para revisão → decisão do grupo → validação final da política → execução se autorizada → armazenamento da saída bruta → retorno resumido ao modelo → interpretação e próxima proposta**. Uma rejeição ou erro de política também retorna ao histórico para que o modelo ajuste a próxima proposta. A próxima ação deve depender da evidência recebida, e não de uma sequência fixa. Limitar a quantidade de passos por investigação e permitir interromper a sessão a qualquer momento.

## 6. Contrato de integração das ferramentas

O desenvolvimento da plataforma fornece o **contrato e o mecanismo de integração**; o usuário adicionará os executáveis e as documentações posteriormente. Para o uso previsto na avaliação, deverá habilitar pelo menos duas ferramentas distintas, sendo ao menos uma capaz de interagir diretamente com o Juice Shop. Exemplos de perfis aceitos após fornecimento e revisão dos recursos:

| Ferramenta | Uso | Entrada permitida | Saída registrada |
| --- | --- | --- | --- |
| Cliente HTTP fornecido pelo usuário | Observar respostas, cabeçalhos e recursos do Juice Shop | Método GET/HEAD inicialmente, caminho relativo, cabeçalhos permitidos, limite de corpo e tempo; outros métodos só após política explícita | Requisição efetiva, status, cabeçalhos, corpo limitado, tempos, erro, referência ao bruto |
| Scanner de portas fornecido pelo usuário | Enumeração limitada do serviço do alvo | Perfil predefinido e porta(s) explicitamente autorizada(s); host substituído pelo IP aprovado do Juice Shop | Parâmetros efetivos, portas observadas, saída completa e código de retorno |

Cada ferramenta adicionada pelo usuário tem manifesto com `id`, versão, executável, perfil/adaptador reconhecido pela plataforma, esquema de entradas e saídas, descrição para o modelo, caminho da documentação, limites de tempo e tamanho, e política de escopo. A documentação, quando fornecida, explica propósito, exemplos, parâmetros e interpretação dos resultados. O modelo escolhe apenas um `id` habilitado e envia **parâmetros estruturados**, nunca uma linha de comando livre. O runner usa argumentos separados (`subprocess` sem `shell=True`) ou chamadas diretas da biblioteca. Não há opção de fornecer script, código, arquivo arbitrário, endereço alternativo ou flags livres ao modelo. O simples fornecimento de um binário e um manifesto não basta para provar que ele respeita o escopo; perfis não reconhecidos ficam indisponíveis até existir um adaptador específico revisado.

## 7. Restrição do alvo e isolamento

O usuário informa uma **URL de sua instância do Juice Shop na LAN** ou escolhe a instância local opcional. O backend valida e normaliza o esquema (`http`/`https`), hostname ou IP, porta e caminho base, confirma que o destino é alcançável e fixa o(s) IP(s) resolvido(s) autorizados para aquela sessão. A URL completa **é mostrada ao modelo** no contexto da investigação, para que ele possa referir-se ao alvo e propor caminhos relativos à aplicação. O backend usa o destino fixado pelo usuário na execução efetiva; o modelo não pode trocar de host ou porta ao propor uma ação. Alterar a URL do campo exige uma nova sessão ou uma redefinição explícita do escopo pelo usuário, registrada nos eventos. A escolha do usuário não autoriza testar outros equipamentos da LAN, serviços externos ou alvos que não sejam o Juice Shop autorizado.

Aplicar as regras abaixo tanto antes de exibir uma ação quanto imediatamente antes de executá-la:

- Somente ferramentas do manifesto habilitadas; argumentos, métodos, caminhos e portas conforme o esquema de cada adaptador. A URL absoluta é aceita **apenas no campo preenchido pelo usuário ao definir o alvo**; propostas do modelo usam caminhos relativos ao URL base. Rejeitar mudança de host ou porta, cabeçalho `Host` arbitrário, proxies HTTP, redirecionamento para outro destino e endereços alternativos embutidos em argumentos. Para HTTP, desabilitar redirecionamentos automáticos ou validar cada salto; conectar apenas ao IP autorizado e revalidar a resolução para impedir que alterações de DNS desviem o tráfego. Preservar o hostname original quando necessário para HTTP/TLS, sem permitir que ele altere o destino da conexão.
- Limitar tempo, número de chamadas, taxa, tamanho de saída e concorrência. Conter erros e encerrar processos que excedam os limites. Restringir caminhos de leitura/escrita aos diretórios da sessão; impedir escapes via `../` e links simbólicos ao exportar arquivos.
- Manter o `executor` em uma rede Docker com **saída controlada para o IP e a porta aprovados da LAN** ou para o serviço local `juice-shop`, além do canal interno com o proxy. O modo LAN requer rota de saída configurada; uma rede Docker marcada `internal` isoladamente não alcançaria o computador do alvo. Aplicar controle de saída no host/gateway ou por mecanismo equivalente, e verificar o bloqueio com tentativas a outros endereços. Montar ferramentas com acesso mínimo e a área de resultados separadamente, sem expor modelos ou o banco de sessões ao executor. Não montar `docker.sock`, não conceder modo privilegiado, limitar recursos e capabilities, executar como usuário sem privilégios e restringir escrita a volumes específicos.
- Tratar páginas, cabeçalhos e saídas das ferramentas como **dados não confiáveis**: instruções encontradas no alvo não alteram a política, não dispensam a aprovação humana e não habilitam novas ferramentas.

O proxy valida pedidos e fornece uma barreira técnica, mas a segurança depende também da rede e do isolamento do executante. A interface não deve alegar que um único teste de IP elimina todos os caminhos de saída. Mudanças de escopo ou inclusão de ferramentas exigem revisão humana e nova configuração; registrar quem realizou a mudança.

## 8. Registros, evidências e relatório

Cada evento recebe identificador, sessão, investigação, data/hora, objetivo e vínculo com o evento anterior. Guardar: texto da proposta, ferramenta e parâmetros originais, parâmetros efetivos após edição, decisão (autorizada, modificada ou rejeitada) e justificativa, validações do proxy, comando/chamada efetivamente executado, código de saída, resultado bruto, resumo enviado ao modelo, interpretação do modelo e decisão posterior do grupo. Armazenar arquivos brutos separadamente com nome seguro, tamanho e hash SHA-256; registrar inclusive ações bloqueadas. Downloads usam apenas arquivos daquela sessão. Ocultar credenciais/tokens na interface e exportações quando cabível, preservando no registro interno a informação necessária à análise.

O gerador da plataforma produz um **rascunho editável**, preenchendo apenas os campos para os quais existam registros: arquitetura e configuração efetivamente usada; plano humano inicial e revisões do modelo; até três investigações (hipótese, estratégia, contribuições do agente, execução, intervenção humana, conclusão e limites); referências a evidências por ID; e campos para análise crítica da IA e um erro ou limitação concreta. Quando esses dados não existirem, sinalizar seções pendentes, sem inventar resultados. O usuário poderá adaptar esse material ao relatório acadêmico de 4 a 6 páginas depois dos testes. Nenhuma conclusão de vulnerabilidade deve aparecer sem evidência correspondente. O exportador pode criar Markdown ou PDF e incluir, em anexo separado, logs completos para verificação; o relatório conciso não precisa transcrever todo o chat.

## 9. Entrega da plataforma e uso posterior

Entregar **somente o código e a configuração da plataforma**: `compose.yaml`, imagens/definições de build do backend, executor, Ollama e interface, código-fonte do proxy, contratos e exemplos *não executáveis* de manifestos, esquema de documentação, estrutura do volume, testes do software com recursos simulados e README com instruções para iniciar, adicionar/registrar modelos, adicionar ferramentas e documentações, verificar recursos, habilitar ferramentas e trocar de modelo. Incluir a opção de iniciar o Juice Shop local como serviço opcional do Compose, sem depender dela para configurar a plataforma.

Depois, **o usuário** instalará os modelos e executáveis no volume persistente, fornecerá as documentações, habilitará as ferramentas e conduzirá as investigações. Para atender ao enunciado acadêmico completo, essa etapa futura precisará incluir pelo menos duas ferramentas integradas, três investigações distintas, restauração documentada do Juice Shop, registros reais, análise crítica, relatório final de 4 a 6 páginas e vídeo de até 10 minutos. Esses resultados não integram a entrega de desenvolvimento da ferramenta. A plataforma deve apenas dar suporte a eles, inclusive com três espaços de investigação e procedimento de reset registrado conforme o modo local ou LAN.

## 10. Critérios de aceitação verificáveis para o software

- A plataforma sobe com `dados/` vazio, mostra o estado **sem modelos e sem ferramentas** e permite configurar o alvo e consultar instruções de instalação sem erro de inicialização.
- Modelos, executáveis e documentações não são incluídos na imagem; arquivos adicionados ao bind mount sobrevivem à recriação dos contêineres e podem ser trocados pelo usuário.
- Varredura automática no início e varredura sob demanda detectam adições, alterações e remoções de modelos e ferramentas; apresentam erros e avisos de documentação ausente, sem executar novos binários nem ativar recursos automaticamente.
- O modelo só aparece como utilizável depois de registrado no Ollama e validado pela API; sua seleção e troca são explícitas e registradas, sem substituir silenciosamente o modelo de uma sessão em andamento.
- Uma ferramenta fornecida pelo usuário só pode ser habilitada se possuir manifesto válido, documentação e perfil/adaptador aceito; alterações depois da revisão suspendem a execução até nova validação.
- Com modelos e ferramentas simulados de teste, o plano humano precede a primeira interação; o agente recebe a URL do alvo, propõe ações com parâmetros estruturados, recebe resultados e pode alterar a proposta seguinte conforme a resposta recebida.
- Nenhuma ferramenta é chamada antes da decisão humana específica; uma ação editada é validada novamente; uma ação rejeitada não é executada; tentativas de outro IP, host ou porta são bloqueadas e registradas.
- O usuário pode baixar o chat, os arquivos da sessão, as saídas das ferramentas e um rascunho do relatório, mesmo quando uma investigação terminou sem conclusão ou quando ainda faltam as três investigações previstas.

## 11. Decisões a confirmar durante a implementação

Definir a topologia exata entre Kali, Docker e computador que hospeda o Juice Shop na LAN; como aplicar a restrição de saída ao IP autorizado; formatos de importação de modelos que serão suportados; perfis/adaptadores de ferramentas previstos no desenvolvimento; permissões do bind mount em cada sistema operacional; limites de recursos; formato final dos anexos e como gerenciar reset em cada modo. Esses detalhes não mudam os requisitos de descoberta sob demanda, escolha explícita dos recursos, supervisão por ação e rastreabilidade.

---

**Base:** enunciado “Avaliação Final — Tecnologias Hackers”, seções 1 a 8. Esta especificação cobre somente o desenvolvimento da plataforma; a instalação dos recursos e as entregas experimentais da avaliação ficam para uso posterior pelo usuário. Escolhas de linguagem, estrutura de código, limites concretos e exemplos de perfis são decisões de projeto.
