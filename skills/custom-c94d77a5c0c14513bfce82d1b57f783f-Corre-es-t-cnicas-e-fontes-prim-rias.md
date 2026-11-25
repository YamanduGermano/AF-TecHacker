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

**Font