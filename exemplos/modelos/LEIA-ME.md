Esta pasta não contém pesos de modelo. Dois caminhos para registrar um modelo no Ollama da plataforma:

* **Ollama pull** (precisa de internet só para esse comando):
  `docker compose -f compose.yaml -f compose.pull.yaml run --rm ollama-pull ollama pull <modelo>`
* **GGUF local**: copie `x.gguf` e `x.Modelfile` (veja `exemplo.Modelfile`) para `dados/modelos/importar/`,
  use «Verificar novos recursos» e «Importar». Só aparecem como utilizáveis os modelos registrados e validados pelo Ollama.
