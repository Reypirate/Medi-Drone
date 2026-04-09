import { createEnv } from "@t3-oss/env-core";
import { z } from "zod";

export const env = createEnv({
  server: {
    NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
    PORT: z.string().transform((v) => parseInt(v, 10)).default("8080"),
  },
  runtimeEnv: process.env,
  skipValidation: !!process.env.CI,
});
