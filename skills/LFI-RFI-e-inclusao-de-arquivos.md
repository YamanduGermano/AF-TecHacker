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
