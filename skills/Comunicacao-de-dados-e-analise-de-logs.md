### TCP e sockets

Um endpoint combina IP e porta; uma conexão TCP é distinguida pelos endpoints de origem e destino. O estabelecimento usa SYN, SYN-ACK e ACK. O encerramento normal envolve FIN/ACK nos dois sentidos; RST pode encerrar abruptamente. TCP organiza a entrega de bytes e controla o fluxo.

### Leitura de captura

Identifique horário, IPs, portas, direção, flags, sequência, ACK, janela e tamanho de dados. No exemplo 1:28(27), há 27 bytes: o limite final é exclusivo. ACK indica o próximo número de sequência esperado. MSS indica o tamanho máximo de dados de um segmento; DF pertence ao IP.

### Caixa de ferramentas

netstat e ss mostram sockets; ss -lntp lista sockets TCP em escuta. tcpdump permite selecionar interface, protocolo, host, rede, porta e direção; -w grava PCAP e -r lê o arquivo. A captura mostra o que é visível à interface, não necessariamente toda a rede. HTTPS não fica legível só por ser capturado.
ARP relaciona endereços IPv4 a endereços MAC no enlace local; o cache evita consultas repetidas. A aula apresenta arp -a, ip neigh, arp-scan, arping e netdiscover. Um vizinho conhecido não equivale a um inventário completo da rede.
### Análise de logs

Correlacione registros de firewall, web, aplicações, SO e IDS/IPS por horário e contexto. Várias falhas SSH podem sugerir tentativa de adivinhação; requisições a caminhos administrativos podem sugerir sondagem. Isso não comprova autenticação ou exploração bem-sucedida. HTTP: 1xx informativo, 2xx sucesso, 3xx redirecionamento, 4xx erro do cliente, 5xx erro do servidor.

### Exercício da aula

A p. 41 pede capturas originadas na máquina, destinadas à máquina, relacionadas ao gateway e de HTTPS, com arquivos separados. Em estudo, explique os filtros antes de executá-los e use somente o ambiente do laboratório.

### Cuidados de interpretação

TTL é apenas pista sobre o SO: varia com configuração e percurso. Normalize fuso horário ao correlacionar eventos. As precisões sobre TCP e PSH estão no caderno de correções