ente responder antes de ler o gabarito. Questões autorais baseadas nas aulas.

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

### 13. Migrar para SaaS tra