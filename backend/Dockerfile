# ResQFlow-X backend (UNVERIFIED in sandbox; build locally).
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic
COPY backend ./backend
COPY routing ./routing
COPY pipeline ./pipeline
ENV RESQFLOW_SECRET=change-me-in-prod
EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
