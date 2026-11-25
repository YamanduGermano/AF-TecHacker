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
