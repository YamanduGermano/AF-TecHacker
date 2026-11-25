Considere método, URL efetivamente testada, status HTTP, cabeçalhos, corpo e erros de transporte separadamente.
Falha de DNS, conexão ou TLS não demonstra comportamento da aplicação. Código de saída de curl e status HTTP são sinais distintos.
Verifique redirecionamentos, autenticação, tipo de conteúdo e se o corpo corresponde ao recurso esperado.
Uma página HTML com status 200 pode ser fallback da SPA, login ou erro personalizado; não prova que um endpoint existe.
Um 401/403 isolado não prova uma vulnerabilidade. Não afirme exploração com base apenas em cabeçalhos ou mensagens.
Compare uma resposta de controle quando isso discriminar a hipótese. Cite os arquivos e declare limites dos trechos.
Mantenha os testes no alvo autorizado; não proponha seguir redirecionamentos para outros destinos sem revisão.