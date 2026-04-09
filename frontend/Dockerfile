FROM oven/bun:canary-slim AS runner
WORKDIR /app

# Copy the build artifacts (bundled server + frontend assets)
COPY build ./build

EXPOSE 8080
CMD ["bun", "build/index.js"]
