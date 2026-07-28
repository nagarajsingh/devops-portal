FROM mashrequae.azurecr.io/cibg/python:3.11-alpine

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Azure DevOps repository-item endpoints may return raw file text instead of
# JSON. Patch the shared response handler so successful non-JSON responses are
# exposed as {"content": <raw text>} for repository template bootstrapping.
RUN python - <<'PY'
from pathlib import Path

path = Path("/app/app/main.py")
content = path.read_text(encoding="utf-8")
old = '''        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw or "{}")
'''
new = '''        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode()
            try:
                body = json.loads(raw or "{}")
            except json.JSONDecodeError:
                body = {"content": raw}
            return response.status, body
'''
if old not in content:
    raise RuntimeError("Expected Azure DevOps response handler was not found")
path.write_text(content.replace(old, new, 1), encoding="utf-8")
PY

RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]