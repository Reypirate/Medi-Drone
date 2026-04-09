import { ChevronRight, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

interface SimulationSidebarProps {
  logs: { msg: string, time: string, type: 'info'|'warn'|'err' }[];
  missions: any[];
  onTriggerPoll: (id: string) => void;
}

export function SimulationSidebar({ logs, missions, onTriggerPoll }: SimulationSidebarProps) {
  return (
    <div className="flex flex-col gap-6">
      {/* Live Simulation Log */}
      <Card className="bg-slate-900 border-slate-800 shadow-2xl">
        <CardHeader className="py-3 px-4 border-b border-slate-800 bg-slate-800/50">
          <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-slate-400 font-mono flex items-center justify-between">
            Live Sim Event Bus
            <Badge variant="outline" className="h-4 text-[8px] bg-green-500/10 text-green-500 border-green-500/30">STREAMING</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[300px]">
            <div className="p-3 font-mono text-[11px] space-y-2">
              {logs.length === 0 ? (
                <div className="text-slate-600 italic text-[10px] text-center pt-10">Monitoring system event pipeline...</div>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-slate-600 whitespace-nowrap">[{log.time}]</span>
                    <span className={log.type === 'err' ? 'text-red-400' : log.type === 'warn' ? 'text-orange-400' : 'text-slate-300'}>
                      {log.msg}
                    </span>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Intervention Table */}
      <Card className="shadow-md border-primary/5">
        <CardHeader className="py-3 border-b bg-muted/20">
          <CardTitle className="text-xs uppercase font-bold tracking-widest">Active Manual Triggers</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[380px]">
            {!missions?.length ? (
              <div className="py-20 text-center text-muted-foreground text-xs italic">No active missions for manual trigger</div>
            ) : (
              <div className="divide-y">
                {missions.map((m: any) => (
                  <div key={m.order_id} className="p-3 hover:bg-muted/30 transition-colors group">
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex flex-col">
                        <span className="text-[10px] font-black font-mono">#{m.order_id.substring(0,8)}</span>
                        <span className="text-[11px] font-bold tracking-tight text-primary uppercase">{m.drone_id}</span>
                      </div>
                      <Button 
                        className="h-6 px-2 text-[9px] font-bold bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground border-primary/20"
                        onClick={() => onTriggerPoll(m.order_id)}
                      >
                        Force Poll Weather
                      </Button>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                      <span className="flex items-center"><ChevronRight className="h-2.5 w-2.5 mr-0.5" /> {m.dispatch_status}</span>
                      <span className="bg-muted px-1.5 py-0.5 rounded italic">ETA: {Math.round(m.eta_minutes)}m</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </CardContent>
        <CardFooter className="py-2 px-3 border-t bg-muted/10">
          <div className="flex items-center gap-2 text-[9px] text-muted-foreground italic">
            <Info className="h-3 w-3" /> Manual triggers bypass the 15s polling cycle for testing.
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
