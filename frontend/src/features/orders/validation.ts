import { z } from "zod";

export const orderSchema = z.object({
  item: z.string().min(1, "Please select a medical item"),
  urgency: z.enum(["ROUTINE", "URGENT", "CRITICAL"]),
  hospital: z.string().optional(),
  addressMode: z.enum(["postal", "coords"]),
  postalCode: z.string().optional(),
  lat: z.string().optional(),
  lng: z.string().optional(),
}).refine((data) => {
  if (data.addressMode === "postal") {
    return !!data.postalCode;
  }
  if (data.addressMode === "coords") {
    return !!data.lat && !!data.lng;
  }
  return true;
}, {
  message: "Invalid address details",
  path: ["addressMode"],
});

export type OrderFormValues = z.infer<typeof orderSchema>;
