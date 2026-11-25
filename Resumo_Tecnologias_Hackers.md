# Resumo das aulas — Tecnologias Hackers

**Guia de estudo | 7 PDFs · 169 páginas de origem**

Sistemas operacionais, redes, reconhecimento, credenciais e segurança web. Material organizado a partir dos anexos da disciplina do Insper, com precisões técnicas identificadas separadamente.

## Roteiro de leitura

1. Sistemas operacionais
2. Comunicação de dados e análise de logs
3. Coleta de informações e Nmap
4. Reconhecendo o alvo, gestão e nuvem
5. Técnicas de reconhecimento web
6. Credenciais e armazenamento de senhas
7. LFI, RFI e inclusão de arquivos
8. Correções técnicas e fontes primárias
9. Questões de revisão com respostas comentadas

### A ideia que conecta as aulas

Observar o sistema, formular hipóteses, reunir evidências e justificar conclusões. Conhecer uma ferramenta ajuda a coletar dados; interpretar esses dados exige entender processos, identidades, comunicação e comportamento das aplicações.

### Como usar

Leia o capítulo, explique os conceitos sem consultar o texto e responda às questões finais. Retorne às páginas indicadas para aprofundar exemplos. As questões são autorais e não representam uma prova oficial.

### Escopo e limites

Este guia é uma síntese, não uma transcrição dos slides. Inclui leitura dos diagramas principais. Handout e arquivos de laboratório mencionados no Blackboard não foram anexados. Complementos e correções estão identificados; nenhuma varredura ou tentativa de autenticação foi executada.

Preparado em 24/11/2026. Numeração das fontes: páginas físicas dos PDFs.

## 1. Sistemas operacionais

**Fonte:** Aula 2 - Sistema Operacional.pdf. 8 páginas; conceitos nas pp. 2-7; laboratório na p. 8.

### Ideia central

Uma ferramenta de segurança executa dentro de um sistema com identidade, estado e recursos. A análise deve seguir: observar, formular hipótese, buscar evidências e justificar a conclusão.

### Programa e processo

Programa é código armazenado; processo é uma instância em execução. Para entendê-lo, correlacione PID, PPID, UID, GID, argumentos, memória, descritores de arquivo, estado e conexões. Ver apenas “python3” não identifica a finalidade nem demonstra que há malware.

### Fronteira de segurança

Aplicações ficam no espaço de usuário e solicitam serviços ao kernel por chamadas de sistema. O kernel medeia CPU, memória, arquivos, rede e dispositivos. O isolamento limita o que cada processo pode acessar.

### Identidade, permissões e recursos

UID/GID e grupos identificam o contexto; permissões rwx, SUID e configurações de serviços influenciam a autorização. A aula mostra o risco da combinação serviço privilegiado + script gravável por qualquer usuário. /proc e logs ajudam a investigar.

### Como aplicar à investigação

Descreva primeiro o fato observado; liste hipóteses alternativas; procure evidências sobre processo pai, usuário e recursos; conclua apenas o que os dados sustentam. Exemplo: um processo desconhecido exige investigação, mas seu nome isolado não permite classificá-lo como malicioso.

### Pergunta de revisão

Por que dois processos do mesmo executável podem representar riscos diferentes? Porque podem executar com usuários, privilégios, argumentos, pais e recursos distintos.

### Limite do material

O handout do laboratório é mencionado, mas não foi anexado. Não há base para reconstruir seus exercícios ou respostas oficiais.

## 2. Comunicação de dados e análise de logs

**Fonte:** Aula 3- Comunicação de dados e Análise de logs.pdf. 55 páginas; ARP pp. 4-8; TCP pp. 10-17; ferramentas pp. 19-40; logs pp. 43-49; descoberta pp. 51-54.

### ARP e comunicação local

ARP relaciona endereços IPv4 a endereços MAC no enlace local; o cache evita consultas repetidas. A aula apresenta arp -a, ip neigh, arp-scan, arping e netdiscover. Um vizinho conhecido não equivale a um inventário completo da rede.

### TCP e sockets

Um endpoint combina IP e porta; uma conexão TCP é distinguida pelos endpoints de origem e destino. O estabelecimento usa SYN, SYN-ACK e ACK. O encerramento normal envolve FIN/ACK nos dois sentidos; RST pode encerrar abruptamente. TCP organiza a entrega de bytes e controla o fluxo.

### Leitura de captura

Identifique horário, IPs, portas, direção, flags, sequência, ACK, janela e tamanho de dados. No exemplo 1:28(27), há 27 bytes: o limite final é exclusivo. ACK indica o próximo número de sequência esperado. MSS indica o tamanho máximo de dados de um segmento; DF pertence ao IP.

### Caixa de ferramentas

netstat e ss mostram sockets; ss -lntp lista sockets TCP em escuta. tcpdump permite selecionar interface, protocolo, host, rede, porta e direção; -w grava PCAP e -r lê o arquivo. A captura mostra o que é visível à interface, não necessariamente toda a rede. HTTPS não fica legível só por ser capturado.

### Análise de logs

Correlacione registros de firewall, web, aplicações, SO e IDS/IPS por horário e contexto. Várias falhas SSH podem sugerir tentativa de adivinhação; requisições a caminhos administrativos podem sugerir sondagem. Isso não comprova autenticação ou exploração bem-sucedida. HTTP: 1xx informativo, 2xx sucesso, 3xx redirecionamento, 4xx erro do cliente, 5xx erro do servidor.

### Exercício da aula

A p. 41 pede capturas originadas na máquina, destinadas à máquina, relacionadas ao gateway e de HTTPS, com arquivos separados. Em estudo, explique os filtros antes de executá-los e use somente o ambiente do laboratório.

### Cuidados de interpretação

TTL é apenas pista sobre o SO: varia com configuração e percurso. Normalize fuso horário ao correlacionar eventos. As precisões sobre TCP e PSH estão no caderno de correções.

## 3. Coleta de informações e Nmap

**Fonte:** Aula 4 - Coleta de informações.pdf. 29 páginas; reconhecimento pp. 2-3 e 11-16; DNS pp. 4-10; Nmap pp. 17-29.

### Objetivo do reconhecimento

Transformar informações dispersas em um inventário de ativos, serviços e possíveis superfícies de exposição. O fluxo mostrado passa por descoberta de hosts, descoberta de serviços e investigação de vulnerabilidades. A aula limita a prática a ambientes autorizados.

### Passivo e ativo

Reconhecimento passivo usa informações já publicadas ou coletadas por terceiros, como resultados de buscadores, RDAP/Whois e Shodan. Reconhecimento ativo interage com a infraestrutura, como ping, traceroute e varreduras. A classificação depende da ação concreta: uma consulta dig envia tráfego ao resolvedor escolhido.

### DNS e estrutura web

DNS é distribuído, hierárquico e utiliza cache. A raiz delega TLDs, que levam aos servidores responsáveis pelos domínios. Os diagramas abordam resolução e DNSSEC. A URL também fornece pistas: esquema, host, caminho e extensão. Informações publicadas ajudam a formular hipóteses sobre a infraestrutura.

### Métodos de varredura

No Nmap, -p seleciona portas, -sS usa sondagens SYN, -sT usa connect(), -sU examina UDP e -sV investiga serviços e versões. -Pn desativa a etapa usual de descoberta de hosts; não elimina filtros. A sintaxe deve ser revisada no manual da versão instalada.

### Estados de portas

open: serviço aceitando comunicação; closed: porta alcançável sem serviço em escuta; filtered: filtragem impede conclusão. unfiltered: alcançável, sem conclusão entre aberta e fechada. open|filtered e closed|filtered expressam ambiguidades. O resultado depende do método e do ponto de observação.

### NSE e validação

O Nmap Scripting Engine amplia os testes, mas cada script tem finalidade e impacto próprios. Banner, versão ou alerta automático são indícios a validar; uma porta aberta não é sinônimo de vulnerabilidade. Registre método, horário, escopo e limitações.

### Correções necessárias

A faixa “0-6535” do slide não cobre todas as portas. O slide também atribui incorretamente open|filtered ao ACK scan. Consulte o caderno de correções antes de ensinar ou reutilizar esses exemplos.

## 4. Reconhecendo o alvo, gestão e nuvem

**Fonte:** Aula - Reconhecendo Alvo.pdf. 16 páginas; ATT&CK pp. 3-6; gestão pp. 8-11; nuvem pp. 12-16.

### MITRE ATT&CK

É uma base estruturada de comportamentos adversários organizada em táticas e técnicas. A aula relaciona seu uso a controles defensivos, threat hunting, detecção, investigação, red team, compartilhamento de conhecimento e resposta a incidentes. Há um exemplo visual de mapeamento de ransomware.

### Comportamento e evidência

Use ATT&CK para organizar o comportamento observado, não como prova automática de autoria ou comprometimento. Complemento didático: tática descreve a finalidade do adversário; técnica descreve como alcançá-la. Identificadores específicos não são necessários para resumir esta aula.

### Gestão de rede

Acompanhar estado de ativos, sistemas e serviços sustenta disponibilidade, desempenho e segurança. O planejamento inclui protocolos, configurações, prioridades, capacidade, custo-benefício, topologia e documentação. QoS e SLA aparecem como objetivos de gestão.

### Reativo e proativo

Gerenciamento reativo atua depois da falha; proativo procura sinais que permitam antecipá-la. Para estudar, conecte indicadores de desempenho e eventos de segurança às hipóteses que eles permitem investigar.

### Modelos de nuvem

Os diagramas mostram nuvem pública, privada e híbrida, além de IaaS, PaaS e SaaS. O nível de controle sobre aplicação, máquinas, armazenamento e rede muda conforme o serviço. O desenho de responsabilidade compartilhada usa AWS como exemplo; não deve virar uma matriz universal para todos os produtos.

### Responsabilidade e prioridades

A divisão entre cliente e provedor precisa ser interpretada para o serviço concreto. A hierarquia apresentada vai de visibilidade a configuração segura, detecção de ameaças, autorremediação e gerenciamento de riscos. Sem visibilidade dos ativos e das configurações, as etapas seguintes ficam prejudicadas.

### Pergunta de revisão

Migrar para a nuvem elimina a responsabilidade do cliente? Não. O material destaca a divisão de responsabilidades, incluindo dados, acessos e configurações conforme o modelo contratado.

## 5. Técnicas de reconhecimento web

**Fonte:** Aula tecnicas de Recon .pdf. 13 páginas; Wapiti/Nikto pp. 2-5; WhatWeb pp. 6-7; ZAP p. 8; DIRB pp. 9-10; WAF e GHDB pp. 11-12.

### Wapiti

A aula apresenta um scanner de aplicações: coleta URLs, testa entradas e produz relatórios de possíveis falhas, incluindo SQL injection, XSS e LFI. O resultado é um candidato à validação, não uma comprovação automática de exploração.

### Nikto

O foco comparativo é o servidor web: configurações, arquivos expostos e problemas conhecidos. Wapiti enfatiza testes dinâmicos nas entradas da aplicação; Nikto enfatiza verificações do servidor. Essa distinção didática não significa que suas capacidades nunca se sobreponham.

### WhatWeb

Identifica indícios de tecnologias, como CMS, frameworks e servidores, usando características das respostas. O slide chama a ferramenta de passiva, mas ela pode enviar requisições ao alvo. Trate identificação de tecnologia como inferência e confira o modo de operação.

### ZAP

A aula introduz a ferramenta de testes de segurança web. Complemento didático: distinguir análise passiva de mensagens disponíveis de varredura ativa que envia testes. O slide não traz um roteiro completo de configuração nem um exercício resolvido.

### DIRB

Enumera caminhos e arquivos por dicionário. O material mostra escolha de wordlist, extensões e filtro de status. “Oculto” significa não encontrado na navegação comum, não necessariamente protegido. Filtrar 403 na saída não concede acesso nem elimina a relevância da resposta.

### wafw00f e GHDB

wafw00f procura sinais de um Web Application Firewall. A Google Hacking Database reúne padrões de busca por exposição de informações. A presença de WAF não prova que a aplicação está segura; ausência de detecção não prova ausência de proteção.

### Como escolher

Pergunte o que precisa descobrir: tecnologia (WhatWeb), configuração do servidor (Nikto), entradas vulneráveis (Wapiti/ZAP), caminhos (DIRB) ou indícios de WAF (wafw00f). Combine resultados com evidências e registre possíveis falsos positivos.

## 6. Credenciais e armazenamento de senhas

**Fonte:** Aula - credenciais.pdf. 22 páginas; ataques pp. 3-5; armazenamento pp. 7-10; wordlists pp. 11-15; ferramentas pp. 16-22.

### Online e offline

Ataques online submetem tentativas ao serviço de autenticação; offline trabalham sobre uma cópia de verificadores de senha, sem consultar o serviço a cada tentativa. A distinção explica por que limites de login não controlam diretamente tentativas offline.

### Dicionário, força bruta e híbrido

Dicionário testa candidatos de uma lista; força bruta percorre combinações de um espaço definido; híbrido transforma candidatos com regras. Rainbow tables usam pré-computação: não são uma tabela universal com todas as senhas possíveis.

### Hash não é criptografia reversível

A descrição dos slides como “reverter” ou “decifrar” hashes é imprecisa. Em uma tentativa offline, calcula-se o verificador de cada candidato e compara-se com o armazenado. Salt individual e funções de derivação adequadas dificultam esse processo; Base64 é apenas codificação.

### Linux e Windows

No Linux, /etc/passwd guarda informações de contas; /etc/shadow guarda verificadores e informações de validade. A aula aborda identificadores de algoritmo, última alteração e limites de troca/expiração. No Windows, aparecem SAM e SYSTEM e a relação histórica com Syskey/bootkey. O trecho Syskey/RC4 deve ser tratado como histórico, não como descrição universal de versões atuais.

### Ferramentas apresentadas

CeWL extrai palavras de conteúdo web; crunch gera combinações; CUPP cria listas por perfil. Hydra aparece em testes online; John the Ripper em verificação offline; samdump2 no exercício com arquivos SAM/SYSTEM. A aula também cita scripts NSE, repositórios e serviços externos. Não enviar hashes ou senhas reais a terceiros como parte de uma revisão.

### Complemento defensivo

Para online: MFA, limitação de tentativas e monitoramento. Para armazenamento: salt individual e função própria para senhas, com custo adequado. Proteger arquivos e backups que contêm verificadores. Essas medidas complementam o foco ofensivo dos slides.

### Limites e revisão

Os arquivos SAM, SYSTEM e shadow do Blackboard não foram anexados. Não alegar quebra de senha nem inventar resultados. Na p. 17, o comando mostrado usa SSH, embora a legenda repita “ftp”.

## 7. LFI, RFI e inclusão de arquivos

**Fonte:** Aula - LFI e RFI 25.pdf. 26 páginas; LFI pp. 4-19; RFI pp. 20-22; shells pp. 23-26.

### Causa principal

A aplicação permite que entrada controlada pelo usuário influencie o arquivo incluído sem restrições adequadas. O exemplo didático usa um parâmetro de página diretamente na função include. Parâmetros com nomes como page ou content são pistas para revisão, não prova de vulnerabilidade.

### LFI versus RFI

LFI envolve arquivo local ao servidor; RFI envolve recurso remoto. LFI pode expor configurações, código ou outros dados que o processo consegue acessar. RFI pode levar à execução de conteúdo remoto quando a linguagem e a configuração permitem. LFI e leitura arbitrária de arquivo são conceitos relacionados, mas não idênticos.

### Caminhos e permissões

A aula relaciona navegação de diretórios à hierarquia de arquivos GNU/Linux e cita exemplos Windows. O impacto depende das permissões do processo e da configuração; não é correto afirmar que qualquer arquivo estará sempre acessível. /etc/passwd descreve contas e não deve ser confundido com /etc/shadow.

### Wrappers e codificação

Os slides mostram o uso de um filtro PHP com Base64 para representar conteúdo e depois decodificá-lo. Base64 não cifra nem protege o conteúdo. A disponibilidade e o comportamento de wrappers dependem da configuração e do mecanismo de inclusão.

### De leitura para execução

O material menciona intoxicação de logs e shells web. A execução por inclusão de logs exige condições adicionais: conteúdo controlável, possibilidade de inclusão e interpretação como código. A cadeia não é consequência automática de toda LFI.

### Shell direta e reversa

Na conexão direta, o alvo escuta e o cliente se conecta; na reversa, o alvo inicia uma conexão de saída. O sentido da conexão afeta a análise de firewall. A aula cita shells PHP históricas; o resumo não inclui nem executa esses artefatos.

### Correção e prevenção

A p. 22 simplifica incorretamente a relação entre LFI/RFI e diretivas PHP. Desabilitar inclusão remota não corrige caminhos locais inseguros. Complemento defensivo: preferir identificadores mapeados a arquivos permitidos, restringir caminhos e privilégios e revisar a origem das entradas.

## 8. Correções técnicas e fontes primárias

As formulações abaixo corrigem ou contextualizam os slides. Conferência em documentação primária em 24/11/2026.

### Nmap: faixa de portas

**Origem:** Coleta, p. 20.

“0-6535” é erro de digitação. -p- seleciona 1-65535; para incluir zero, especificar -p 0-65535.

**Fonte primária:** [https://nmap.org/book/man-port-specification.html](https://nmap.org/book/man-port-specification.html)

### Nmap: estados

**Origem:** Coleta, p. 25.

ACK scan pode retornar unfiltered; a associação do slide com open|filtered está incorreta.

**Fonte primária:** [https://nmap.org/book/man-port-scanning-basics.html](https://nmap.org/book/man-port-scanning-basics.html)

### Nmap: descoberta

**Origem:** Coleta, p. 21.

Usar -Pn como opção documentada para pular descoberta de hosts; isso não desativa o firewall.

**Fonte primária:** [https://nmap.org/book/man-host-discovery.html](https://nmap.org/book/man-host-discovery.html)

### PHP: diretivas

**Origem:** LFI/RFI, p. 22.

allow_url_include controla inclusão por wrappers de URL e depende de allow_url_fopen. Nenhuma dessas opções substitui a correção de LFI.

**Fonte primária:** [https://www.php.net/manual/en/filesystem.configuration.php](https://www.php.net/manual/en/filesystem.configuration.php)

### Windows: Syskey

**Origem:** Credenciais, pp. 8-9.

O utilitário syskey.exe foi retirado das versões modernas, incluindo Windows 10 1709. Tratar a explicação como histórica.

**Fonte primária:** [https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/syskey-exe-utility-is-no-longer-supported](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/syskey-exe-utility-is-no-longer-supported)

### WhatWeb: interação

**Origem:** Técnicas de Recon, p. 6.

Até o modo menos agressivo envia requisição HTTP. “Passivo” aqui não significa ausência de contato com o alvo.

**Fonte primária:** [https://github.com/urbanadventurer/WhatWeb/blob/master/README.md](https://github.com/urbanadventurer/WhatWeb/blob/master/README.md)

### TCP: sequência e PSH

**Origem:** Comunicação, pp. 14 e 33-35.

TCP numera bytes; ACK aponta a próxima sequência esperada. PSH não é garantia absoluta de entrega à aplicação.

**Fonte primária:** [https://www.rfc-editor.org/rfc/rfc9293.html](https://www.rfc-editor.org/rfc/rfc9293.html)

### Senhas: hashes

**Origem:** Credenciais, pp. 3-5 e 19.

Hash não se decifra: candidatos são comparados. Salt individual combate pré-computação; funções próprias para senhas aumentam o custo.

**Fonte primária:** [https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

### Outras precisões de leitura

Credenciais, p. 17: o comando usa SSH, embora a legenda repita FTP. Comunicação, p. 7: `ip neigh show dev eth0` filtra a interface; `ip neigh show 192.168.1.1` filtra o endereço. TTL é pista, não identificação definitiva de SO. Sucesso HTTP não comprova sucesso de exploração.

## 9. Questões de revisão com respostas comentadas

Tente responder antes de ler o gabarito. Questões autorais baseadas nas aulas.

### 1. Um processo chamado python3 é malware?

**Resposta:** Não é possível concluir pelo nome. Investigue pai, usuário, argumentos, arquivos, conexões e contexto.

**Base:** Sistemas, pp. 3-7.

### 2. Qual a diferença entre programa e processo?

**Resposta:** Programa é código; processo é uma instância em execução com identidade, estado e recursos.

**Base:** Sistemas, p. 4.

### 3. O que identifica uma conexão TCP?

**Resposta:** O par de endpoints: IP e porta de origem, IP e porta de destino, no contexto TCP.

**Base:** Comunicação, pp. 15-17.

### 4. O que significa 1:28(27) em uma captura?

**Resposta:** São 27 bytes; 28 é o limite final exclusivo. A sequência seguinte esperada é 28.

**Base:** Comunicação, p. 35; precisão técnica no caderno de correções.

### 5. Várias falhas de senha comprovam invasão?

**Resposta:** Não. Sugerem tentativas e exigem correlação com sucesso de login e outros eventos.

**Base:** Comunicação, p. 47.

### 6. Uma porta filtered está fechada?

**Resposta:** Não se pode afirmar: a filtragem impede determinar seu estado.

**Base:** Coleta, p. 24.

### 7. Uma porta open comprova vulnerabilidade?

**Resposta:** Não. Indica serviço acessível; uma falha precisa de evidência adicional.

**Base:** Coleta, pp. 24-28; síntese didática.

### 8. Quando usar Wapiti ou Nikto?

**Resposta:** Wapiti enfatiza entradas da aplicação; Nikto, configuração e problemas do servidor web.

**Base:** Técnicas de Recon, pp. 2-5.

### 9. O que muda entre ataque online e offline?

**Resposta:** No online, tentativas passam pelo serviço; no offline, candidatos são testados contra verificadores disponíveis localmente.

**Base:** Credenciais, p. 3.

### 10. Por que não afirmar que um hash foi “descriptografado”?

**Resposta:** Hash não possui operação inversa de descriptografia. A recuperação usual testa candidatos e compara resultados.

**Base:** Credenciais, pp. 3-5; correção OWASP.

### 11. Qual a diferença entre LFI e RFI?

**Resposta:** A primeira inclui recurso local; a segunda envolve recurso remoto, quando a configuração permite.

**Base:** LFI/RFI, pp. 5-6 e 20.

### 12. Desligar allow_url_include resolve toda LFI?

**Resposta:** Não. Caminhos locais inseguros continuam exigindo correção na aplicação.

**Base:** LFI/RFI, p. 22; correção PHP.

### 13. Migrar para SaaS transfere toda responsabilidade ao provedor?

**Resposta:** Não. A divisão muda, mas dados, identidade e outras obrigações do cliente persistem conforme o serviço.

**Base:** Reconhecendo Alvo, pp. 14-15.

### 14. Como ATT&CK ajuda uma investigação?

**Resposta:** Organiza comportamentos e apoia relacionar detecções e controles a táticas/técnicas, sem provar autoria por si só.

**Base:** Reconhecendo Alvo, pp. 3-6; síntese didática.