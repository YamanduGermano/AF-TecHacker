# http-client — cliente HTTP para o Juice Shop de laboratório

## Propósito
Faz **uma** requisição HTTP ao alvo da sessão e registra a resposta bruta. É a ferramenta de observação básica:
ver o que um endpoint devolve, quais cabeçalhos e cookies aparecem, como a aplicação reage a entradas simples.

## Parâmetros (todos estruturados; não existe campo de host, porta, URL absoluta, proxy ou flags)
| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `metodo` | sim | `GET` ou `HEAD` (outros métodos só se a política global e a do manifesto os permitirem) |
| `caminho` | sim | Caminho relativo começando com `/`, p. ex. `/rest/products/search?q=apple` |
| `cabecalhos` | não | Objeto `{nome: valor}`; só nomes presentes na política do manifesto |
| `max_corpo_bytes` | não | Limite de bytes de corpo registrados |
| `timeout_s` | não | Limitado pelo manifesto |

## Exemplo de proposta
```json
{"tipo": "proposta", "ferramenta": "http-client",
 "parametros": {"metodo": "GET", "caminho": "/rest/products/search?q=apple"},
 "justificativa": "Observar a resposta da busca antes de qualquer variação"}
```

## Como interpretar o resultado
* `status`, `linha_status` e `cabecalhos`: indicam como o servidor trata o pedido (`Content-Type`, `Set-Cookie`, `Server`…).
* `corpo_amostra`: pode vir truncado em `max_corpo_bytes`; `corpo_truncado` avisa. `ip_remoto` deve ser o IP autorizado
  (se diferir, o campo `alerta` aparece).
* Um status 200 **não prova** vulnerabilidade; um erro 500 **não prova** exploração. Só o resultado bruto registrado
  e a interpretação do grupo contam como evidência.
* Redirecionamentos **não** são seguidos: o `Location` é devolvido para o grupo decidir o próximo passo.
