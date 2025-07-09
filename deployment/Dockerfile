# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project into the container
COPY . .

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1  
# Prevent Python from writing .pyc files
ENV PYTHONUNBUFFERED=1         
# Ensure output is logged immediately

# Copy entrypoint.sh explicitly (from ./deployment to /app/)
COPY deployment/entrypoint.sh ./entrypoint.sh

# Make it executable
RUN chmod +x ./entrypoint.sh

# Default command
CMD ["./entrypoint.sh"]
