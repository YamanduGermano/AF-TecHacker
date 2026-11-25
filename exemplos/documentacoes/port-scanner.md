# port-scanner — verificação de portas TCP do alvo autorizado

## Propósito
Confirma quais portas **explicitamente autorizadas na criação da sessão** respondem no IP aprovado do alvo.
Serve para validar o escopo (a porta do Juice Shop deve estar aberta) — não para descobrir outros serviços.

## Parâmetros
| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `perfil` | sim | `conectar_tcp` (handshake TCP) ou `versao_servico` (identificação leve de versão) |
| `portas` | sim | Lista de inteiros; só portas autorizadas na sessão (a porta da URL já vem autorizada) |
| `timeout_s` | não | Limitado pelo manifesto |

O host é sempre o IP aprovado do alvo. Scripts NSE, faixas de portas livres e flags livres não existem.

## Exemplo de proposta
```json
{"tipo": "proposta", "ferramenta": "port-scanner",
 "parametros": {"perfil": "conectar_tcp", "portas": [3000]},
 "justificativa": "Confirmar que a porta do Juice Shop está aberta no IP autorizado"}
```

## Como interpretar o resultado
* `portas[]` traz `porta`, `proto`, `estado`, `servico` e `versao`. `open`: a porta aceitou a conexão; `closed`/`filtered`: sem serviço ou filtrada por firewall.
* Resultado de varredura descreve **o instante da execução**; repita se o alvo foi reiniciado.
