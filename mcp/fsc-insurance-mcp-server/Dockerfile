FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fsc_core.py catalog.json server.py ./

# Cloud Run이 PORT를 주입한다. 로컬 실행 시의 기본값.
ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
