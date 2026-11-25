FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY agente/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proxy ./proxy
COPY agente ./agente
# O compose define o usuário (PLATAFORMA_UID/GID) para que os arquivos em dados/ pertençam ao usuário do host.
USER 10001
EXPOSE 8000
CMD ["uvicorn", "agente.app:criar_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
