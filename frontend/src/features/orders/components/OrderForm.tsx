import { useForm } from '@tanstack/react-form';
import { MapPin, Check, X, AlertTriangle, ExternalLink } from 'lucide-react';
import { orderSchema } from '../validation';
import { useOrderMutations } from '../hooks/use-order-mutations';
import { useGeocoding } from '../hooks/use-geocoding';
import { 
  CardContent, 
  CardHeader, 
  CardTitle, 
  CardDescription 
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function OrderForm({ onSuccess }: { onSuccess?: () => void }) {
  const { submitOrder } = useOrderMutations();
  const { validation, checkAddress, confirmAddress, resetValidation } = useGeocoding();

  const form = useForm({
    defaultValues: {
      item: '',
      urgency: 'CRITICAL' as 'ROUTINE' | 'URGENT' | 'CRITICAL',
      hospital: '',
      quantity: 1,
      addressMode: 'postal' as 'postal' | 'coords',
      postalCode: '',
      addressDetails: '',
      lat: '',
      lng: '',
    },
    validators: {
      onChange: ({ value }) => {
        const result = orderSchema.safeParse(value);
        if (result.success) return undefined;
        return (result as any).error.issues[0]?.message ?? "Invalid data";
      },
    },
    onSubmit: async ({ value }) => {
      if (!validation.data || !validation.isConfirmed) return;

      let customerAddress = validation.data.formatted_address;
      if (value.addressDetails) {
        customerAddress = `${value.addressDetails}, ${customerAddress}`;
      }

      submitOrder.mutate({
        hospital_id: value.hospital === 'auto' || !value.hospital ? null : value.hospital,
        item_id: value.item,
        quantity: value.quantity,
        urgency_level: value.urgency,
        customer_address: customerAddress,
        customer_coords: validation.data.customer_coords,
      }, {
        onSuccess: () => {
          form.reset();
          resetValidation();
          onSuccess?.();
        }
      });
    },
  });

  const useMyLocation = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      form.setFieldValue('addressMode', 'coords');
      form.setFieldValue('lat', pos.coords.latitude.toFixed(6));
      form.setFieldValue('lng', pos.coords.longitude.toFixed(6));
    });
  };

  return (
    <>
      <CardHeader className="pb-4">
        <CardTitle className="text-xl flex items-center gap-2">
          <span className="p-1.5 bg-primary/10 rounded-lg text-primary text-sm font-bold">🚨 Dispatch</span>
          Emergency Request
        </CardTitle>
        <CardDescription className="text-xs">Configure payload and destination for drone dispatch</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            form.handleSubmit();
          }}
          className="flex flex-col gap-5 text-sm"
        >
          <div className="space-y-3">
            <Label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Payload Details</Label>
            <div className="grid grid-cols-1 gap-3">
              <form.Field
                name="item"
                children={(field) => (
                  <div className="space-y-1.5">
                    <Label htmlFor={field.name}>Medical Item</Label>
                    <Select value={field.state.value} onValueChange={(val: string | null) => field.handleChange(val ?? '')}>
                      <SelectTrigger id={field.name} className="h-9">
                        <SelectValue placeholder="-- Select Item --" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="DEFIB_001">Automated External Defibrillator</SelectItem>
                        <SelectItem value="EPI_001">Epinephrine Auto-injector</SelectItem>
                        <SelectItem value="BLOOD_O_NEG">O-Negative Blood Unit</SelectItem>
                        <SelectItem value="ANTIVENOM_001">Snake Antivenom</SelectItem>
                        <SelectItem value="INSULIN_001">Insulin Vial</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              />

              <div className="grid grid-cols-2 gap-3">
                <form.Field
                  name="quantity"
                  children={(field) => (
                    <div className="space-y-1.5">
                      <Label htmlFor={field.name}>Quantity</Label>
                      <Input
                        id={field.name}
                        type="number"
                        min="1"
                        className="h-9"
                        value={field.state.value}
                        onChange={(e) => field.handleChange(Number(e.target.value))}
                      />
                    </div>
                  )}
                />

                <form.Field
                  name="urgency"
                  children={(field) => (
                    <div className="space-y-1.5">
                      <Label>Urgency</Label>
                      <div className="flex p-0.5 bg-muted rounded-md h-9">
                        {['ROUTINE', 'URGENT', 'CRITICAL'].map((level) => (
                          <button
                            key={level}
                            type="button"
                            onClick={() => field.handleChange(level as any)}
                            className={`flex-1 text-[10px] font-bold rounded px-1 transition-all ${
                              field.state.value === level
                                ? 'bg-background shadow-sm text-primary'
                                : 'text-muted-foreground hover:text-foreground'
                            }`}
                          >
                            {level === 'CRITICAL' ? '⚡' : ''} {level}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                />
              </div>
            </div>
          </div>

          <form.Field
            name="hospital"
            children={(field) => (
              <div className="space-y-3">
                <Label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Dispatch Source (Optional)</Label>
                <Select value={field.state.value} onValueChange={(val: string | null) => field.handleChange(val ?? '')}>
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="Auto-select Nearest Hospital" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto-select Nearest Hospital</SelectItem>
                    <SelectItem value="HOSP_001">Central General Hospital</SelectItem>
                    <SelectItem value="HOSP_002">Northside Medical Center</SelectItem>
                    <SelectItem value="HOSP_003">Westend Clinic</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          />

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Destination Delivery</Label>
              <Button type="button" variant="link" size="sm" className="h-auto p-0 text-[10px] text-primary" onClick={useMyLocation}>
                <MapPin className="h-3 w-3 mr-1" /> Use My Location
              </Button>
            </div>

            <form.Subscribe
              selector={(state) => [state.values.addressMode]}
              children={([addressMode]) => (
                <Tabs value={addressMode as string} onValueChange={(v) => { 
                  form.setFieldValue('addressMode', v as any);
                  resetValidation();
                }}>
                  <TabsList className="grid w-full grid-cols-2 h-8">
                    <TabsTrigger value="postal" className="text-xs">Postal Code</TabsTrigger>
                    <TabsTrigger value="coords" className="text-xs">Coordinates</TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="postal" className="space-y-3 mt-3">
                    <form.Field
                      name="postalCode"
                      children={(field) => (
                        <Input 
                          placeholder="Enter 6-digit SGP Postal Code" 
                          value={field.state.value} 
                          onChange={(e) => field.handleChange(e.target.value)}
                          className="h-9"
                        />
                      )}
                    />
                    <form.Field
                      name="addressDetails"
                      children={(field) => (
                        <Input 
                          placeholder="Unit #, Floor, Building Info (Optional)" 
                          value={field.state.value} 
                          onChange={(e) => field.handleChange(e.target.value)}
                          className="h-9"
                        />
                      )}
                    />
                  </TabsContent>
                  
                  <TabsContent value="coords" className="grid grid-cols-2 gap-3 mt-3">
                    <form.Field
                      name="lat"
                      children={(field) => (
                        <Input placeholder="Latitude" value={field.state.value} onChange={(e) => field.handleChange(e.target.value)} className="h-9" />
                      )}
                    />
                    <form.Field
                      name="lng"
                      children={(field) => (
                        <Input placeholder="Longitude" value={field.state.value} onChange={(e) => field.handleChange(e.target.value)} className="h-9" />
                      )}
                    />
                  </TabsContent>
                </Tabs>
              )}
            />

            {!validation.data ? (
              <Button 
                type="button" 
                variant="secondary" 
                className="w-full h-9 border-dashed border-2" 
                onClick={() => checkAddress(form.state.values.addressMode, form.state.values)}
                disabled={validation.isLoading}
              >
                {validation.isLoading ? 'Resolving Geocode...' : 'Check Address Validity'}
              </Button>
            ) : (
              <div className={`p-3 rounded-lg border-2 ${validation.data.region_valid ? 'bg-primary/5 border-primary/20' : 'bg-destructive/5 border-destructive/20'}`}>
                <div className="flex justify-between items-start gap-2 mb-2">
                  <div className="space-y-0.5">
                    <div className={`text-[10px] font-bold uppercase ${validation.data.region_valid ? 'text-primary' : 'text-destructive'}`}>
                      {validation.data.region_valid ? '✅ Serviceable Address' : '❌ Out of Range'}
                    </div>
                    <div className="text-xs font-medium leading-tight">{validation.data.formatted_address}</div>
                  </div>
                  <Button type="button" variant="ghost" size="icon" className="h-6 w-6" onClick={resetValidation}>
                    <X className="h-3 w-3" />
                  </Button>
                </div>

                {validation.data.region_valid ? (
                  <div className="flex flex-col gap-2">
                    <div className="grid grid-cols-2 gap-2 text-[10px] text-muted-foreground bg-background p-2 rounded">
                      <div>Coords: <span className="text-foreground">{validation.data.customer_coords.lat.toFixed(4)}, {validation.data.customer_coords.lng.toFixed(4)}</span></div>
                      <div>Country: <span className="text-foreground">{validation.data.country}</span></div>
                    </div>
                    <div className="flex gap-2 items-center text-[10px]">
                      <a 
                        href={`https://www.google.com/maps?q=${validation.data.customer_coords.lat},${validation.data.customer_coords.lng}`}
                        target="_blank" rel="noopener noreferrer"
                        className="flex items-center text-primary underline"
                      >
                        <ExternalLink className="h-2.5 w-2.5 mr-1" /> View Map
                      </a>
                      {!validation.isConfirmed && (
                        <Button 
                          type="button" 
                          size="sm" 
                          className="h-6 text-[10px] px-2 ml-auto"
                          onClick={confirmAddress}
                        >
                          Confirm Address
                        </Button>
                      )}
                      {validation.isConfirmed && (
                        <Badge variant="outline" className="ml-auto text-primary border-primary bg-primary/5 h-6 text-[10px]">
                          <Check className="h-3 w-3 mr-1" /> Confirmed
                        </Badge>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="text-[10px] text-destructive flex items-center gap-1 mt-1">
                    <AlertTriangle className="h-3 w-3" /> Drone delivery only supports Singapore coordinates.
                  </div>
                )}
              </div>
            )}
          </div>

          {submitOrder.isError && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-md text-[11px] leading-snug">
              <strong>Submission Failed:</strong> {submitOrder.error?.message}
            </div>
          )}

          <form.Subscribe
            selector={(state) => [state.canSubmit, state.isSubmitting]}
            children={([canSubmit, isSubmitting]) => (
              <Button
                type="submit"
                disabled={!canSubmit || isSubmitting || !validation.isConfirmed}
                className="w-full h-11 text-base font-bold shadow-lg mt-2 disabled:opacity-50"
              >
                {isSubmitting || submitOrder.isPending ? 'Initiating Dispatch...' : 'Dispatch Drone'}
              </Button>
            )}
          />
        </form>
      </CardContent>
    </>
  );
}
