FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md* ./
COPY finance_mcp ./finance_mcp

RUN uv pip install --system --no-cache -e .

ENV FINANCE_MCP_HOST=0.0.0.0 \
    FINANCE_MCP_PORT=7800

EXPOSE 7800

CMD ["finance-mcp"]
