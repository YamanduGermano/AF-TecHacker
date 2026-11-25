FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ARG EXTRA_APT_PACKAGES=""
# Apenas dependências genéricas. Nenhuma ferramenta de segurança é instalada na imagem: os executáveis são
# fornecidos por você em dados/ferramentas/. Use EXECUTOR_EXTRA_APT só para bibliotecas de execução delas.
RUN if [ -n "$EXTRA_APT_PACKAGES" ]; then apt-get update && apt-get install -y --no-install-recommends $EXTRA_APT_PACKAGES && rm -rf /var/lib/apt/lists/*; fi
WORKDIR /app
COPY executor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proxy ./proxy
COPY executor ./executor
USER 10001
EXPOSE 8001
CMD ["uvicorn", "executor.service:app", "--host", "0.0.0.0", "--port", "8001"]
