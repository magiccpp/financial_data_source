FROM python:3.9-slim-buster

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code (including your main.py or similar)
COPY . .

# Set environment variables if needed (e.g., you could copy the .env here)
# RUN python -c "import os; print(os.environ.get('AZURE_STORAGE_CONNECTION_STRING'))"  # Optional: Verify env vars

# Expose port 8000 (or your chosen port)
EXPOSE 8000

# Define the command to run your application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]