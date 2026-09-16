# Playwright 공식 Python 베이스 이미지 (모든 브라우저 의존성 내장)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# 필수 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 및 리소스 복사
COPY src/ ./src/
COPY templates/ ./templates/
COPY config.example.json .

# 기본 데이터 디렉토리 생성
RUN mkdir -p data

# 포트 노출 (웹 대시보드)
EXPOSE 5000

# 환경변수 기본값
ENV PYTHONUNBUFFERED=1

# 웹 대시보드 실행
CMD ["python", "src/web_app.py"]
