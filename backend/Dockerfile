FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
COPY presenter_agent/requirements.txt presenter_agent/requirements.txt
COPY researcher_agent/requirements.txt researcher_agent/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt \
    && pip install --no-cache-dir -r presenter_agent/requirements.txt \
    && pip install --no-cache-dir -r researcher_agent/requirements.txt \
    && playwright install chromium && playwright install-deps

COPY backend/ backend/
COPY presenter_agent/ presenter_agent/
COPY researcher_agent/ researcher_agent/

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
