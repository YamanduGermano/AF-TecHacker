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