FROM node:22-alpine
RUN npm install -g @bitbonsai/mcpvault@0.16.0 supergateway@4.0.0 && npm cache clean --force
USER node
EXPOSE 8000
# mcpvault speaks stdio; supergateway exposes it as Streamable HTTP at /mcp
CMD ["supergateway", "--stdio", "mcpvault /vault", \
     "--outputTransport", "streamableHttp", "--stateful", "--sessionTimeout", "3600000", \
     "--port", "8000", "--healthEndpoint", "/healthz", "--logLevel", "info"]
