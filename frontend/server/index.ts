import { Hono } from "hono";
import { serveStatic } from "hono/bun";
import { env } from "./env";

const app = new Hono();

// Forwarding Gateway (Kong)
const GATEWAY_URL = Bun.env.UPSTREAM_GATEWAY_URL || "http://kong:8000";

// Health check endpoint
app.get("/health", (c) => {
  return c.json({ status: "healthy", timestamp: new Date().toISOString() });
});

// Proxy logic for API requests
app.all("/api/*", async (c) => {
  const url = new URL(c.req.url);
  const targetUrl = `${GATEWAY_URL}${url.pathname}${url.search}`;
  
  console.log(`📡 PROXY: ${c.req.method} ${url.pathname} -> ${targetUrl}`);
  
  const headers = new Headers(c.req.header());
  // Remove host header to allow the proxy target to set its own
  headers.delete("host");

  const response = await fetch(targetUrl, {
    method: c.req.method,
    headers: headers,
    body: ["GET", "HEAD"].includes(c.req.method) ? undefined : await c.req.arrayBuffer(),
  });

  return new Response(response.body, {
    status: response.status,
    headers: response.headers,
  });
});

// Serve static assets from the build directory
app.use("/assets/*", serveStatic({ root: "./build" }));
app.use("/*", serveStatic({ root: "./build" }));

// Fallback all other requests to index.html for SPA routing
app.get("*", serveStatic({ path: "./build/index.html" }));

console.log(` Medi-Drone Hono Server running on http://localhost:${env.PORT}`);

export default {
  port: env.PORT,
  fetch: app.fetch,
};
