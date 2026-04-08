import { useForm } from '@tanstack/react-form';
import { MapPin, Trash2, Plus, Activity } from 'lucide-react';
import { hazardZoneSchema } from '../validation';
import { 
  Card, 
  CardContent, 
  CardHeader, 
  CardTitle, 
  CardDescription 
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useState } from 'react';

interface HazardZone {
  lat: number;
  lng: number;
  radius_km: number;
  id: number;
  name?: string;
}

const HAZARD_PRESETS: HazardZone[] = [
  { name: "Central Singapore", lat: 1.3521, lng: 103.8198, radius_km: 1.5, id: 1 },
  { name: "Marina Bay", lat: 1.2834, lng: 103.8607, radius_km: 1.2, id: 2 },
  { name: "Changi Airport", lat: 1.3644, lng: 103.9915, radius_km: 2.0, id: 3 },
  { name: "Jurong West", lat: 1.3404, lng: 103.7090, radius_km: 1.8, id: 4 },
];

interface HazardManagerProps {
  onActivate: (zones: HazardZone[]) => void;
  isPending: boolean;
}

export function HazardManager({ onActivate, isPending }: HazardManagerProps) {
  const [hazardZones, setHazardZones] = useState<HazardZone[]>([]);

  const form = useForm({
    defaultValues: {
      lat: '',
      lng: '',
      radius: '1.5',
    },
    validators: {
      onChange: ({ value }) => {
        const result = hazardZoneSchema.safeParse(value);
        if (result.success) return undefined;
        return (result as any).error.issues[0]?.message ?? "Invalid hazard data";
      },
    },
    onSubmit: async ({ value }) => {
      const newHazard: HazardZone = {
        lat: parseFloat(value.lat),
        lng: parseFloat(value.lng),
        radius_km: parseFloat(value.radius),
        id: Date.now()
      };
      setHazardZones(prev => [...prev, newHazard]);
      form.reset();
    },
  });

  const removeHazard = (id: number) => {
    setHazardZones(prev => prev.filter(h => h.id !== id));
  };

  const applyPreset = (preset: HazardZone) => {
    setHazardZones(prev => [...prev, { ...preset, id: Date.now() }]);
  };

  return (
    <Card className="border-primary/20 shadow-xl overflow-hidden h-fit">
      <div className="h-1 bg-primary" />
      <CardHeader>
          <CardTitle className="text-xl font-black text-primary italic tracking-tighter uppercase">GEO-FENCE NAVIGATIONAL HAZARDS</CardTitle>
          <CardDescription>Inject localized hazard spheres to force A* path calculation across the simulation grid.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-4">
                <Label className="text-xs uppercase font-bold tracking-widest text-muted-foreground">Manual Position Injection</Label>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    form.handleSubmit();
                  }}
                  className="space-y-4"
                >
                  <div className="grid grid-cols-2 gap-3">
                    <form.Field
                      name="lat"
                      children={(field) => (
                        <div className="space-y-1.5">
                            <Label className="text-[10px]">Latitude</Label>
                            <Input className="h-9 font-mono text-xs" placeholder="1.2345" value={field.state.value} onChange={e => field.handleChange(e.target.value)} />
                        </div>
                      )}
                    />
                    <form.Field
                      name="lng"
                      children={(field) => (
                        <div className="space-y-1.5">
                            <Label className="text-[10px]">Longitude</Label>
                            <Input className="h-9 font-mono text-xs" placeholder="103.819" value={field.state.value} onChange={e => field.handleChange(e.target.value)} />
                        </div>
                      )}
                    />
                  </div>
                  <form.Field
                    name="radius"
                    children={(field) => (
                      <div className="space-y-1.5">
                        <Label className="text-[10px]">Hazard Radius (KM)</Label>
                        <div className="flex gap-3">
                          <Input className="h-9 font-mono text-xs" placeholder="1.5" value={field.state.value} onChange={e => field.handleChange(e.target.value)} />
                          <Button type="submit" size="icon" className="h-9 w-9 shrink-0"><Plus className="h-4 w-4" /></Button>
                        </div>
                      </div>
                    )}
                  />
                </form>

                <div className="pt-2">
                    <Label className="text-xs uppercase font-bold tracking-widest text-muted-foreground">Regional Presets</Label>
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      {HAZARD_PRESETS.map((p, idx) => (
                          <Button key={idx} variant="outline" className="h-8 text-[10px] font-bold tracking-tight justify-start" onClick={() => applyPreset(p)}>
                            <MapPin className="h-3 w-3 mr-2 opacity-50" /> {p.name}
                          </Button>
                      ))}
                    </div>
                </div>
              </div>

              <div className="flex flex-col">
                <Label className="text-xs uppercase font-bold tracking-widest text-muted-foreground mb-3">Defined Hazard Zones ({hazardZones.length})</Label>
                <ScrollArea className="flex-1 bg-muted/30 rounded-lg p-3 border h-[240px]">
                    {hazardZones.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-[200px] opacity-20 italic text-xs grayscale">
                          <Activity className="h-10 w-10 mb-2" />
                          No zones defined
                      </div>
                    ) : (
                      <div className="space-y-2">
                          {hazardZones.map(h => (
                            <div key={h.id} className="flex justify-between items-center p-2 bg-background border rounded shadow-[2px_2px_0_0_rgba(0,0,0,0.05)]">
                                <div className="flex flex-col">
                                  <span className="text-[10px] font-mono leading-none">({h.lat.toFixed(4)}, {h.lng.toFixed(4)})</span>
                                  <span className="text-[10px] font-black text-primary uppercase pt-0.5">{h.radius_km} KM RADIUS</span>
                                </div>
                                <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive hover:bg-destructive/10" onClick={() => removeHazard(h.id)}>
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                          ))}
                      </div>
                    )}
                </ScrollArea>
                <Button variant="secondary" size="sm" className="mt-2 text-[10px] font-bold h-7" onClick={() => setHazardZones([])}>CLEAR ALL ZONES</Button>
              </div>
          </div>

          <Button 
            className="w-full h-12 font-black italic tracking-tight shadow-lg shadow-primary/10" 
            onClick={() => onActivate(hazardZones)} 
            disabled={hazardZones.length === 0 || isPending}
          >
            {isPending ? 'ENGAGING SEQUENCE...' : 'ENGAGE GRID REROUTE SEQUENCE'}
          </Button>
      </CardContent>
    </Card>
  );
}
