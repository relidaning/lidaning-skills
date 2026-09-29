FROM node:22-alpine
RUN npm install -g @bitbonsai/mcpvault@0.16.0 supergateway@4.0.0 && npm cache clean --force
# mcpvault plus the excluded-folders filter (see start.js, config/excluded-dirs)
COPY start.js /usr/local/lib/node_modules/@bitbonsai/mcpvault/dist/start.js
USER node
EXPOSE 8000
# mcpvault speaks stdio; supergateway exposes it as Streamable HTTP at /mcp
CMD ["supergateway", "--stdio", "node /usr/local/lib/node_modules/@bitbonsai/mcpvault/dist/start.js /vault", \
     "--outputTransport", "streamableHttp", "--stateful", "--sessionTimeout", "3600000", \
     "--port", "8000", "--healthEndpoint", "/healthz", "--logLevel", "none"]
