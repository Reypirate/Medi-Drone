import { useForm } from '@tanstack/react-form';
import { Wind, CloudRain, Zap, RotateCcw } from 'lucide-react';
import { cancelSettingsSchema } from '../validation';
import { 
  Card, 
  CardContent, 
  CardHeader, 
  CardTitle, 
  CardDescription 
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";

interface SimulationControlsProps {
  onActivate: (values: any) => void;
  isPending: boolean;
}

export function SimulationControls({ onActivate, isPending }: SimulationControlsProps) {
  const form = useForm({
    defaultValues: {
      wind: 65,
      rain: 15,
      highWind: true,
      heavyRain: true,
      thunderstorm: true,
      tornado: false,
    },
    validators: {
      onChange: ({ value }) => {
        const result = cancelSettingsSchema.safeParse(value);
        if (result.success) return undefined;
        return (result as any).error.issues[0]?.message ?? "Invalid environmental settings";
      },
    },
    onSubmit: async ({ value }) => {
      const reasons = [];
      if (value.highWind) reasons.push('HIGH_WIND');
      if (value.heavyRain) reasons.push('HEAVY_RAIN');
      if (value.thunderstorm) reasons.push('THUNDERSTORM');
      if (value.tornado) reasons.push('TORNADO');

      onActivate({
        force_unsafe: true,
        unsafe_reason: reasons.length ? reasons : ['HIGH_WIND'],
        wind_speed_kmh: value.wind,
        rain_mm: value.rain,
        hazard_zones: [],
      });
    },
  });

  return (
    <Card className="border-destructive/20 shadow-xl overflow-hidden">
      <div className="h-1 bg-destructive" />
      <CardHeader>
        <CardTitle className="text-xl font-black text-destructive italic tracking-tighter">ENVIRONMENT OVERRIDE</CardTitle>
        <CardDescription>Force adverse weather conditions globally across the network to trigger mission aborts.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-8">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            form.handleSubmit();
          }}
          className="space-y-8"
        >
          <div className="grid grid-cols-2 gap-8">
            <div className="space-y-3">
              <Label className="text-xs uppercase font-bold tracking-widest">Atmospheric Force</Label>
              <div className="space-y-4 pt-2">
                <form.Field
                  name="wind"
                  children={(field) => (
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="flex items-center"><Wind className="h-3 w-3 mr-1" /> Wind Velocity</span>
                        <span className="font-bold">{field.state.value} KM/H</span>
                      </div>
                      <input 
                        type="range" 
                        min="0" 
                        max="150" 
                        value={field.state.value} 
                        onChange={e => field.handleChange(+e.target.value)}
                        className="w-full h-1 bg-muted rounded-lg appearance-none cursor-pointer accent-destructive" 
                      />
                    </div>
                  )}
                />
                <form.Field
                  name="rain"
                  children={(field) => (
                    <div className="space-y-1 pt-2">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="flex items-center"><CloudRain className="h-3 w-3 mr-1" /> Rain Intensity</span>
                        <span className="font-bold">{field.state.value} MM/H</span>
                      </div>
                      <input 
                        type="range" 
                        min="0" 
                        max="60" 
                        value={field.state.value} 
                        onChange={e => field.handleChange(+e.target.value)}
                        className="w-full h-1 bg-muted rounded-lg appearance-none cursor-pointer accent-destructive" 
                      />
                    </div>
                  )}
                />
              </div>
            </div>

            <div className="space-y-3">
              <Label className="text-xs uppercase font-bold tracking-widest">Active Hazards</Label>
              <div className="grid grid-cols-1 gap-2 pt-2">
                {[
                  { id: 'highWind', label: 'Hurricane Conditions', icon: <Wind className="h-3 w-3" /> },
                  { id: 'heavyRain', label: 'Flood Intensity', icon: <CloudRain className="h-3 w-3" /> },
                  { id: 'thunderstorm', label: 'Electrical Storm', icon: <Zap className="h-3 w-3" /> },
                  { id: 'tornado', label: 'Vortex Warning', icon: <RotateCcw className="h-3 w-3" /> },
                ].map((item: any) => (
                  <form.Field
                    key={item.id}
                    name={item.id as any}
                    children={(field) => (
                      <div className="flex items-center justify-between p-2 rounded-lg border bg-muted/20 group hover:border-destructive/30 transition-colors">
                        <label htmlFor={item.id} className="text-xs font-bold flex items-center cursor-pointer select-none">
                          <span className="p-1 bg-destructive/10 rounded mr-2 text-destructive">{item.icon}</span>
                          {item.label}
                        </label>
                        <Checkbox 
                          id={item.id} 
                          checked={field.state.value} 
                          onCheckedChange={c => field.handleChange(c === true)} 
                        />
                      </div>
                    )}
                  />
                ))}
              </div>
            </div>
          </div>
          
          <div className="flex gap-4">
            <Button 
              type="button" 
              variant="secondary" 
              className="flex-1 font-bold h-12" 
              onClick={() => form.reset()}
            >
              RESET DEFAULTS
            </Button>
            <form.Subscribe
              selector={(state) => [state.canSubmit, state.isSubmitting]}
              children={([canSubmit, isSubmitting]) => (
                <Button 
                  type="submit" 
                  variant="destructive" 
                  disabled={!canSubmit || isSubmitting || isPending}
                  className="flex-[2] font-black italic tracking-tight h-12 shadow-lg shadow-destructive/20"
                >
                  {isSubmitting || isPending ? 'INITIATING...' : 'INITIATE CANCELLATION OVERRIDE'}
                </Button>
              )}
            />
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
