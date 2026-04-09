import { useState } from 'react';
import { useActiveMissions } from '../features/orders/hooks/use-orders';
import { useSimulationStatus, useSimulationMutations } from '../features/simulation/hooks/use-simulation';
import { SimulationControls } from '../features/simulation/components/SimulationControls';
import { HazardManager } from '../features/simulation/components/HazardManager';
import { SimulationSidebar } from '../features/simulation/components/SimulationSidebar';
import { ShieldAlert, Zap, FastForward, RotateCcw } from 'lucide-react';
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function Simulation() {
  const { data: statusData } = useSimulationStatus();
  const { data: missionsData } = useActiveMissions();
  const { 
    logs, 
    disableMutation, 
    activateSimulation, 
    fastForwardMutation, 
    emergencyResetMutation, 
    triggerPollMutation 
  } = useSimulationMutations();
  
  const [activeTab, setActiveTab] = useState<'mode1' | 'mode2'>('mode1');
  
  const isFastForward = statusData?.config?.fast_forward?.enabled;

  return (
    <div className="max-w-7xl mx-auto p-6 mt-4 grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-8">
      {/* Main Control Panel */}
      <div className="flex flex-col gap-6">
        <div className="flex justify-between items-center">
            <div>
                <h1 className="text-3xl font-black italic tracking-tighter uppercase">Simulation Core</h1>
                <p className="text-muted-foreground text-sm font-medium">Stress test flight systems and A* grid navigation.</p>
            </div>
            <div className="flex gap-2">
                <Button 
                    variant={isFastForward ? "default" : "outline"} 
                    className={`h-9 font-bold ${isFastForward ? 'bg-orange-600 hover:bg-orange-700 animate-pulse' : ''}`}
                    onClick={() => fastForwardMutation.mutate(!isFastForward)}
                >
                    <FastForward className="h-4 w-4 mr-2" />
                    {isFastForward ? 'FFWD ACTIVE (4X)' : 'Fast Forward'}
                </Button>
                <Button variant="outline" className="h-9 hover:bg-destructive hover:text-destructive-foreground font-bold" onClick={() => emergencyResetMutation.mutate()}>
                    <RotateCcw className="h-4 w-4 mr-2" />
                    EMERGENCY RESET
                </Button>
            </div>
        </div>

        {/* Global Status Banner */}
        <Card className={`overflow-hidden border-2 h-[80px] flex items-center px-6 ${statusData?.simulation_enabled ? 'bg-orange-500/10 border-orange-500/30' : 'bg-green-500/10 border-green-500/30'}`}>
            <div className="flex-1 flex items-center gap-4">
               <div className={`p-2 rounded-full ${statusData?.simulation_enabled ? 'bg-orange-500 text-white' : 'bg-green-500 text-white animate-pulse shadow-sm'}`}>
                  {statusData?.simulation_enabled ? <ShieldAlert className="h-5 w-5" /> : <Zap className="h-5 w-5" />}
               </div>
               <div>
                  <div className="text-xs uppercase font-black tracking-widest opacity-60">System Environment</div>
                  <div className={`text-lg font-black italic tracking-tighter ${statusData?.simulation_enabled ? 'text-orange-600' : 'text-green-600'}`}>
                    {statusData?.simulation_enabled ? 'HAZARDOUS SIMULATION ACTIVE' : 'REAL-TIME DATA MODE'}
                  </div>
               </div>
            </div>
            {statusData?.simulation_enabled && (
                <Button variant="outline" size="sm" className="border-orange-500/30 hover:bg-orange-500/20 font-bold" onClick={() => disableMutation.mutate()}>
                   TERMINATE SIMULATION
                </Button>
            )}
        </Card>

        {/* Modes Matrix */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-full">
            <TabsList className="grid grid-cols-2 p-1 bg-muted h-12">
                <TabsTrigger value="mode1" className="h-10 text-xs font-bold uppercase tracking-widest data-[state=active]:bg-destructive data-[state=active]:text-destructive-foreground">
                    ⚡ Mode 1: Static Cancellation
                </TabsTrigger>
                <TabsTrigger value="mode2" className="h-10 text-xs font-bold uppercase tracking-widest data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                    🌍 Mode 2: Grid-Based Rerouting
                </TabsTrigger>
            </TabsList>

            <TabsContent value="mode1" className="mt-6">
               <SimulationControls 
                  onActivate={(payload) => activateSimulation.mutate(payload)} 
                  isPending={activateSimulation.isPending} 
               />
            </TabsContent>

            <TabsContent value="mode2" className="mt-6">
               <HazardManager 
                  onActivate={(zones) => activateSimulation.mutate({ force_unsafe: false, hazard_zones: zones })}
                  isPending={activateSimulation.isPending}
               />
            </TabsContent>
        </Tabs>
      </div>

      {/* Sidebar: Logs and Active Missions */}
      <SimulationSidebar 
        logs={logs} 
        missions={missionsData?.active_missions || []} 
        onTriggerPoll={(id) => triggerPollMutation.mutate(id)} 
      />
    </div>
  );
}
