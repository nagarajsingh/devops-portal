FROM mashrequae.azurecr.io/cibg/python:3.11-alpine

WORKDIR /app
RUN apk add --no-cache curl ca-certificates
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "import openpyxl, reportlab; print('openpyxl', openpyxl.__version__); print('reportlab', reportlab.Version)"
COPY app ./app
RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8000"]
