FROM python:3.12-slim

# Empeche Python d'ecrire des .pyc et force la sortie non bufferisee
# (sans ca, les logs n'apparaissent pas en temps reel dans docker logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Paris

WORKDIR /app

# Les dependances AVANT le code : cette couche est mise en cache et n'est
# reconstruite que si requirements.txt change (voir explication plus bas).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Utilisateur non-root : un conteneur compromis n'a pas les droits admin
RUN useradd --create-home appuser \
    && mkdir -p /app/data /app/models \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
