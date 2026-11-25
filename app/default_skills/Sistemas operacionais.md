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
