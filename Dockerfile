FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && \
    apt-get install --no-install-recommends -y libasound2 && \
    apt-get clean && rm -rf /var/lib/apt/lists/
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "app.py"]
