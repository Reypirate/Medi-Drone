import { useMemo } from 'react';
import { useDrones } from '../features/fleet/hooks/use-drones';
import { useActiveMissions } from '../features/orders/hooks/use-orders';
import { DroneDashboard, type DroneItem } from '../features/fleet/components/DroneDashboard';

export function Drones() {
  const { data: drones, isLoading, isFetching } = useDrones();
  const { data: missionsData } = useActiveMissions();

  const activeMissions = missionsData?.active_missions || [];
  const missionsByDrone = useMemo(() => {
    const map: Record<string, any> = {};
    activeMissions.forEach((m: any) => { map[m.drone_id] = m; });
    return map;
  }, [activeMissions]);

  return (
    <div className="max-w-6xl mx-auto p-6 mt-4 flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-3xl font-black tracking-tight uppercase italic">Fleet Telemetry</h1>
        <p className="text-muted-foreground text-sm">Real-time status and battery metrics for the autonomous drone network.</p>
      </div>

      <DroneDashboard 
        drones={(drones || []) as DroneItem[]} 
        missionsByDrone={missionsByDrone} 
        isLoading={isLoading} 
        isFetching={isFetching} 
      />
    </div>
  );
}
