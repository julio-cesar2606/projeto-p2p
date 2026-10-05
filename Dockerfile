FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY src/ /app/src/
CMD ["python", "src/no_p2p.py"]
