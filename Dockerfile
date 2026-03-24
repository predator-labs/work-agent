FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y git openssh-client curl nodejs npm && \
    rm -rf /var/lib/apt/lists/*

# Pre-populate Bitbucket known hosts
RUN ssh-keyscan bitbucket.org >> /etc/ssh/ssh_known_hosts

# Install Claude Code CLI (required by claude-agent-sdk)
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory for state
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
