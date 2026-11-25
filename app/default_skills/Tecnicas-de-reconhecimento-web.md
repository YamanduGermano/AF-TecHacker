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