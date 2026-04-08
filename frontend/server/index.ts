import { Hono } from "hono";
import { serveStatic } from "hono/bun";
import { env } from "./env";

const app = new Hono();

// Health check endpoint
app.get("/health", (c) => {
  return c.json({ status: "healthy", timestamp: new Date().toISOString() });
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
