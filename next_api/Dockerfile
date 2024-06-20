FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY next_api.py next_api.py

CMD ["uvicorn", "next_api:app", "--host", "0.0.0.0", "--port", "8001"]

