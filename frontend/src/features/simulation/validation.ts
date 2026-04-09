import { z } from "zod";

export const cancelSettingsSchema = z.object({
  wind: z.number().min(0).max(150),
  rain: z.number().min(0).max(60),
  highWind: z.boolean(),
  heavyRain: z.boolean(),
  thunderstorm: z.boolean(),
  tornado: z.boolean(),
});

export const hazardZoneSchema = z.object({
  lat: z.string().refine((v) => !isNaN(parseFloat(v)), "Invalid latitude"),
  lng: z.string().refine((v) => !isNaN(parseFloat(v)), "Invalid longitude"),
  radius: z.string().refine((v) => !isNaN(parseFloat(v)) && parseFloat(v) > 0, "Radius must be positive"),
});

export type CancelSettingsValues = z.infer<typeof cancelSettingsSchema>;
export type HazardZoneValues = z.infer<typeof hazardZoneSchema>;
