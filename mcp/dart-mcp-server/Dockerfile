FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 빌드 시점에 구운 자산. 런타임에 만들 수 없다 —
# corpCode.xml 다운로드는 실측 약 4분이 걸린다. build_assets.py로 갱신한다.
COPY assets/ ./assets/
COPY server.py .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
