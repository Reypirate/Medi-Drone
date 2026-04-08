import { createEnv } from "@t3-oss/env-core";
import { z } from "zod";

export const env = createEnv({
  clientPrefix: "VITE_",
  client: {
    VITE_GOOGLE_MAPS_API_KEY: z.string().min(1, "Google Maps API Key is required"),
  },
  runtimeEnv: import.meta.env,
  skipValidation: !!import.meta.env.SSR,
});
