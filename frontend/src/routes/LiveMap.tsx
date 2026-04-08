/// <reference types="@types/google.maps" />
declare const google: any;
import { useEffect, useState } from 'react';
import { APIProvider, Map, AdvancedMarker, useMap, InfoWindow } from '@vis.gl/react-google-maps';
import { useDrones } from '../features/fleet/hooks/use-drones';
import { useActiveMissions } from '../features/orders/hooks/use-orders';
import { useSimulationStatus } from '../features/simulation/hooks/use-simulation';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Plane, Activity, Navigation } from 'lucide-react';

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || 'YOUR_API_KEY_HERE';
const SINGAPORE_CENTER = { lat: 1.3521, lng: 103.8198 };

// --- Custom Map Components ---

function Polyline({ paths, color, weight = 3, dashed = false }: { paths: any[], color: string, weight?: number, dashed?: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!map || !paths.length) return;

    const line = new google.maps.Polyline({
      path: paths,
      geodesic: true,
      strokeColor: color,
      strokeOpacity: dashed ? 0 : 0.8,
      strokeWeight: weight,
      map: map,
    });

    if (dashed) {
      line.setOptions({
        strokeOpacity: 0,
        icons: [{
          icon: { path: "M 0,-1 0,1", strokeOpacity: 0.5, scale: weight },
          offset: "0",
          repeat: "12px",
        }],
      });
    }

    return () => line.setMap(null);
  }, [map, paths, color, weight, dashed]);
  return null;
}

function Circle({ center, radius, color, opacity = 0.2 }: { center: any, radius: number, color: string, opacity?: number }) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    const circle = new google.maps.Circle({
      strokeColor: color,
      strokeOpacity: 0.8,
      strokeWeight: 2,
      fillColor: color,
      fillOpacity: opacity,
      map,
      center,
      radius: radius * 1000, // KM to M
    });
    return () => circle.setMap(null);
  }, [map, center, radius, color, opacity]);
  return null;
}

// --- Main Map Component ---

export default function LiveMap() {
  const [selectedDroneId, setSelectedDroneId] = useState<string | null>(null);
  const { data: drones = [] } = useDrones();
  const { data: missionsData } = useActiveMissions();
  const { data: simStatus } = useSimulationStatus();

  const activeMissions = missionsData?.active_missions || [];
  const hazardZones = simStatus?.simulation_enabled ? (simStatus.config?.hazard_zones || []) : [];

  return (
    <div className="relative w-full h-[calc(100vh-73px)] overflow-hidden bg-slate-950">
      <APIProvider apiKey={API_KEY}>
        <Map
          defaultCenter={SINGAPORE_CENTER}
          defaultZoom={12}
          mapId="MEDIDRONE_LIVE_MAP"
          className="w-full h-full"
          disableDefaultUI={true}
          gestureHandling={'greedy'}
          styles={[
            { elementType: "geometry", stylers: [{ color: "#0f172a" }] },
            { elementType: "labels.text.fill", stylers: [{ color: "#64748b" }] },
            { featureType: "water", elementType: "geometry", stylers: [{ color: "#020617" }] },
            { featureType: "road", elementType: "geometry", stylers: [{ color: "#1e293b" }] },
          ]}
        >
          {/* Mission Flight Paths */}
          {activeMissions.map((m: any) => {
             const isRerouted = m.dispatch_status === 'REROUTED_IN_FLIGHT';
             
             // 1. Point from Hospital to Current (Completed/Active Path)
             if (m.current_coords && m.hospital_coords) {
                // If we have waypoints (A* reroute), use them
                if (m.waypoints && m.waypoints.length > 0) {
                   return (
                     <Polyline 
                        key={m.order_id} 
                        paths={[m.hospital_coords, ...m.waypoints, m.customer_coords]} 
                        color="#22c55e" 
                        weight={3} 
                     />
                   );
                } else {
                   // Straight line path
                   return (
                      <Polyline 
                        key={m.order_id} 
                        paths={[m.hospital_coords, m.customer_coords]} 
                        color={isRerouted ? "#f97316" : "#3b82f6"} 
                        weight={3} 
                     />
                   );
                }
             }
             return null;
          })}

          {/* Destination & Hospital Waypoints */}
          {drones.map((d: any) => {
             const mission = activeMissions.find((m: any) => m.drone_id === d.drone_id);
             return (
               <div key={d.drone_id}>
                 <AdvancedMarker 
                   position={{ lat: d.lat, lng: d.lng }}
                   onClick={() => setSelectedDroneId(d.drone_id)}
                 >
                   <div className={`p-2 rounded-full border-2 border-white shadow-xl transition-transform hover:scale-110 cursor-pointer ${
                      d.status === 'FAULTY' ? 'bg-red-500 shadow-red-500/50' :
                      d.status === 'LOW_BATTERY' ? 'bg-orange-500 shadow-orange-500/50' :
                      mission ? 'bg-primary shadow-primary/50' : 'bg-green-500 shadow-green-500/50'
                   }`}>
                      <Plane className="h-4 w-4 text-white" />
                   </div>
                 </AdvancedMarker>

                 {selectedDroneId === d.drone_id && (
                   <InfoWindow
                     position={{ lat: d.lat, lng: d.lng }}
                     onCloseClick={() => setSelectedDroneId(null)}
                   >
                     <div className="p-3 min-w-[200px] text-slate-100 font-sans">
                        <div className="flex items-center justify-between mb-2 border-b border-slate-700 pb-2">
                           <span className="font-bold text-sm tracking-tight">{d.drone_id}</span>
                           <Badge variant={d.status === 'OPERATIONAL' ? 'default' : 'destructive'} className="text-[10px] h-5">
                              {d.status}
                           </Badge>
                        </div>
                        <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-[11px] mb-3">
                           <div className="text-slate-400">Battery</div>
                           <div className="flex items-center gap-2">
                              <span className={d.battery < 20 ? 'text-red-500 font-bold' : ''}>{d.battery}%</span>
                              <div className="h-1.5 w-12 bg-slate-800 rounded-full overflow-hidden">
                                 <div 
                                    className={`h-full ${d.battery < 20 ? 'bg-red-500' : d.battery < 50 ? 'bg-yellow-500' : 'bg-green-500'}`} 
                                    style={{ width: `${d.battery}%` }}
                                 />
                              </div>
                           </div>
                           <div className="text-slate-400">Position</div>
                           <div className="font-mono">{d.lat.toFixed(4)}, {d.lng.toFixed(4)}</div>
                           {mission && (
                              <>
                                 <div className="text-slate-400">Mission</div>
                                 <div className="text-primary font-bold">#{mission.order_id.substring(0,8)}</div>
                                 <div className="text-slate-400">ETA</div>
                                 <div>{Math.round(mission.eta_minutes)} mins</div>
                              </>
                           )}
                        </div>
                        {mission && (
                           <div className="text-[10px] bg-slate-800/50 p-2 rounded border border-slate-700 text-slate-300">
                             En-route to delivery...
                           </div>
                        )}
                     </div>
                   </InfoWindow>
                 )}
               </div>
             );
          })}

          {/* Hazard Zones */}
          {hazardZones.map((z: any) => (
             <Circle 
                key={z.id} 
                center={{ lat: z.lat, lng: z.lng }} 
                radius={z.radius_km || 1.5} 
                color="#ef4444" 
                opacity={0.15} 
             />
          ))}
        </Map>
      </APIProvider>

      {/* Control Panels */}
      <div className="absolute top-6 left-6 flex flex-col gap-4 pointer-events-none">
         <Card className="w-80 bg-slate-950/80 backdrop-blur-md border-slate-800 shadow-2xl pointer-events-auto overflow-hidden">
            <div className="h-1 bg-primary" />
            <CardHeader className="p-4 pb-2">
               <CardTitle className="text-xs font-black uppercase tracking-widest text-slate-400 flex items-center justify-between">
                  Mission Visualization
                  <Badge variant="outline" className="h-4 text-[9px] bg-green-500/10 text-green-500 border-green-500/30">LIVE</Badge>
               </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-2">
               <div className="grid grid-cols-2 gap-2 mb-4">
                  <div className="flex items-center gap-2 p-2 bg-slate-900 rounded border border-slate-800">
                     <div className="w-2 h-2 rounded-full bg-primary shadow-[0_0_8px_rgba(168,85,247,0.5)]" />
                     <span className="text-[10px] font-bold text-slate-300">IN FLIGHT</span>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-slate-900 rounded border border-slate-800">
                     <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]" />
                     <span className="text-[10px] font-bold text-slate-300">AVAILABLE</span>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-slate-900 rounded border border-slate-800">
                     <div className="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]" />
                     <span className="text-[10px] font-bold text-slate-300">FAULTY</span>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-slate-900 rounded border border-slate-800">
                     <div className="w-[12px] h-[2px] bg-[#f97316]" />
                     <span className="text-[10px] font-bold text-slate-300">RE-ROUTE</span>
                  </div>
               </div>

               <div className="space-y-3">
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                     <span className="flex items-center gap-1.5"><Plane className="h-3 w-3" /> Active Drones</span>
                     <span className="font-mono text-white font-bold">{activeMissions.length}</span>
                  </div>
                  {simStatus?.simulation_enabled && (
                    <div className="flex items-center justify-between text-[11px] text-orange-400 font-bold bg-orange-400/5 p-2 rounded border border-orange-400/20">
                       <span className="flex items-center gap-1.5">Hazard Warnings</span>
                       <span className="font-mono">{hazardZones.length} ZONES</span>
                    </div>
                  )}
               </div>
            </CardContent>
         </Card>

         <Card className="w-80 bg-slate-950/80 backdrop-blur-md border-slate-800 shadow-2xl pointer-events-auto">
            <CardHeader className="p-3 border-b border-slate-800 bg-slate-900/50">
               <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-slate-500 flex items-center gap-2">
                  <Activity className="h-3 w-3" /> Active Deployments
               </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
               <ScrollArea className="h-60">
                  {activeMissions.length === 0 ? (
                    <div className="py-10 text-center text-[11px] text-slate-600 italic font-mono">No active telemetry...</div>
                  ) : (
                    <div className="divide-y divide-slate-800">
                       {activeMissions.map((m: any) => (
                          <div key={m.order_id} className="p-3 hover:bg-slate-900 transition-colors">
                             <div className="flex justify-between items-start mb-1">
                                <span className="text-[10px] font-mono font-bold text-primary italic">#{m.order_id.substring(0,8)}</span>
                                <Badge variant="outline" className="h-4 text-[8px] border-slate-700 text-slate-400">{m.dispatch_status}</Badge>
                             </div>
                             <div className="flex justify-between items-center text-[10px]">
                                <span className="text-slate-300 flex items-center gap-1"><Navigation className="h-2.5 w-2.5" /> Drone {m.drone_id}</span>
                                <span className="text-white font-bold">ETA {Math.round(m.eta_minutes)}m</span>
                             </div>
                          </div>
                       ))}
                    </div>
                  )}
               </ScrollArea>
            </CardContent>
         </Card>
      </div>
    </div>
  );
}
