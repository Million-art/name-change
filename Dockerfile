FROM python:3.9-slim

# Set working directory inside container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files from current directory to /app in container
COPY . .

# Add the container's working directory to Python path
# This helps Python find modules in the src directory
ENV PYTHONPATH=/app

# Create a non-root user for security
RUN useradd -m botuser
RUN chown -R botuser:botuser /app
USER botuser

# Run the bot
CMD ["python", "src/main.py"] 