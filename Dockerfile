FROM python:3.11-slim

WORKDIR /app

# Dependencies first so a code change does not invalidate the pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user rather than root.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# App Runner routes to 8080 by default, and the server must bind 0.0.0.0
# to be reachable from outside the container.
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
