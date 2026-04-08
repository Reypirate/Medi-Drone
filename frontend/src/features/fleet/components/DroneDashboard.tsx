import { useMemo } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table';
import { Plane, BatteryFull, BatteryLow, BatteryWarning, AlertTriangle, ShieldCheck, MapPin, Activity } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type DroneItem = {
  drone_id: string;
  status: string;
  battery: number;
  lat: number;
  lng: number;
};

const columnHelper = createColumnHelper<DroneItem>();

interface DroneDashboardProps {
  drones: DroneItem[];
  missionsByDrone: Record<string, any>;
  isLoading: boolean;
  isFetching: boolean;
}

export function DroneDashboard({ drones, missionsByDrone, isLoading, isFetching }: DroneDashboardProps) {
  const allDrones = useMemo(() => {
    // Sort: In flight first, then low battery, then operational
    return [...drones].sort((a, b) => {
      const aInFlight = missionsByDrone[a.drone_id] ? 1 : 0;
      const bInFlight = missionsByDrone[b.drone_id] ? 1 : 0;
      if (aInFlight !== bInFlight) return bInFlight - aInFlight;
      
      const aLow = a.battery < 20 ? 1 : 0;
      const bLow = b.battery < 20 ? 1 : 0;
      if (aLow !== bLow) return bLow - aLow;
      
      return a.drone_id.localeCompare(b.drone_id);
    });
  }, [drones, missionsByDrone]);

  const columns = useMemo(
    () => [
      columnHelper.accessor('drone_id', {
        header: 'Unit designation',
        cell: (info) => (
          <div className="flex items-center gap-3">
             <div className="p-2 bg-primary/10 rounded-lg">
               <Plane className="h-4 w-4 text-primary" />
             </div>
             <div className="flex flex-col">
               <span className="font-bold text-sm tracking-tight">{info.getValue()}</span>
               <span className="text-[10px] text-muted-foreground font-mono">MD-SERIES V2</span>
             </div>
          </div>
        ),
      }),
      columnHelper.accessor('battery', {
        header: 'Power Cell',
        cell: (info) => {
          const val = info.getValue();
          let color = 'bg-primary';
          let Icon = BatteryFull;
          
          if (val < 20) { color = 'bg-destructive'; Icon = BatteryLow; }
          else if (val < 50) { color = 'bg-yellow-500'; Icon = BatteryWarning; }
          
          return (
            <div className="flex flex-col gap-1.5 w-[120px]">
              <div className="flex justify-between items-center px-0.5">
                <span className={`text-[10px] font-bold flex items-center gap-1 ${val < 20 ? 'text-destructive' : 'text-muted-foreground'}`}>
                   <Icon className="h-3 w-3" /> {val}%
                </span>
              </div>
              <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                <div className={`h-full ${color} transition-all duration-500`} style={{ width: `${val}%` }} />
              </div>
            </div>
          );
        },
      }),
      columnHelper.accessor('status', {
        header: 'Status',
        cell: (info) => {
          const drone = info.row.original;
          const mission = missionsByDrone[drone.drone_id];
          const displayStatus = mission ? (mission.dispatch_status || 'IN_FLIGHT') : drone.status;

          let variant: 'default' | 'secondary' | 'destructive' | 'outline' = 'outline';
          let icon = null;

          if (displayStatus === 'OPERATIONAL') {
            variant = 'default';
            icon = <ShieldCheck className="h-3 w-3 mr-1" />;
          } else if (displayStatus.includes('FLIGHT') || displayStatus.includes('TRANSIT') || displayStatus.includes('HOSPITAL') || displayStatus.includes('CUSTOMER')) {
            variant = 'secondary';
            icon = <Activity className="h-3 w-3 mr-1 animate-pulse" />;
          } else if (displayStatus === 'FAULTY' || displayStatus === 'LOW_BATTERY') {
            variant = 'destructive';
            icon = <AlertTriangle className="h-3 w-3 mr-1" />;
          }

          return (
            <Badge variant={variant} className="text-[10px] py-0.5 h-6 px-2 rounded-md uppercase font-bold tracking-tight">
              {icon}
              {displayStatus.replace(/_/g, ' ')}
            </Badge>
          );
        },
      }),
      columnHelper.display({
        id: 'mission_details',
        header: 'Active Deployment',
        cell: (info) => {
          const drone = info.row.original;
          const mission = missionsByDrone[drone.drone_id];
          if (!mission) return <span className="text-muted-foreground text-[11px] italic">No active assignment</span>;
          
          return (
            <div className="flex flex-col gap-0.5">
               <div className="text-[11px] font-medium flex items-center gap-1">
                 <span className="text-primary font-bold"># {mission.order_id.substring(0,8)}</span>
                 <span className="text-muted-foreground opacity-50">•</span>
                 <span>ETA {Math.round(mission.eta_minutes || 0)}m</span>
               </div>
               <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                  <MapPin className="h-2.5 w-2.5" />
                  {mission.dispatch_status === 'TO_HOSPITAL' ? 'En-route to Hospital' : 'Flying to Destination'}
               </div>
            </div>
          );
        },
      })
    ],
    [missionsByDrone]
  );

  const table = useReactTable({
    data: allDrones,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const operational = allDrones.filter(d => d.status === 'OPERATIONAL').length;
  const inFlight = Object.keys(missionsByDrone).length;
  const faulty = allDrones.filter(d => d.status === 'FAULTY').length;
  const lowBat = allDrones.filter(d => d.status === 'LOW_BATTERY' || (d.status === 'OPERATIONAL' && d.battery < 30)).length;

  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Fleet', value: allDrones.length, sub: 'Units Online', color: 'text-foreground' },
          { label: 'Operational', value: operational, sub: 'Ready for Dispatch', color: 'text-primary' },
          { label: 'In Flight', value: inFlight, sub: 'Active Missions', color: 'text-blue-500' },
          { label: 'Maintenance', value: faulty + lowBat, sub: 'Repair or Charge', color: 'text-destructive' },
        ].map((stat) => (
          <Card key={stat.label} className="border-primary/5 shadow-sm overflow-hidden relative">
            <CardContent className="p-6">
               <div className={`text-4xl font-black ${stat.color}`}>{stat.value}</div>
               <div className="text-[11px] font-bold uppercase tracking-wider mt-1">{stat.label}</div>
               <div className="text-[10px] text-muted-foreground">{stat.sub}</div>
               <div className="absolute -right-2 -bottom-2 opacity-1 scale-150">
                 <Plane className="h-20 w-20 text-muted-foreground/10" />
               </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="border-primary/10 shadow-lg">
        <CardHeader className="flex flex-row justify-between items-center border-b pb-4 bg-muted/20">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              Autonomous Systems Overview
            </CardTitle>
            <CardDescription className="text-xs">Live feed of all robotic assets and their current tasks</CardDescription>
          </div>
          {isFetching && (
            <Badge variant="outline" className="animate-pulse bg-primary/5 border-primary/20 text-primary h-6 text-[10px] font-mono">
              📡 UPDATING DATA
            </Badge>
          )}
        </CardHeader>
        <CardContent className="pt-6">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
              <div className="relative">
                <div className="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
                <Plane className="h-4 w-4 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-primary" />
              </div>
              <span className="text-sm font-bold tracking-widest text-muted-foreground uppercase">Syncing Fleet...</span>
            </div>
          ) : allDrones.length === 0 ? (
            <div className="text-center py-20 text-muted-foreground bg-muted/30 rounded-xl border-2 border-dashed">
              <div className="text-2xl mb-2">🔭</div>
              <p className="font-bold">No drones found in sector</p>
              <p className="text-xs opacity-60">Register new units via the administrative gateway.</p>
            </div>
          ) : (
            <div className="rounded-xl border overflow-hidden">
              <Table>
                <TableHeader className="bg-muted/50">
                  {table.getHeaderGroups().map((headerGroup) => (
                    <TableRow key={headerGroup.id} className="hover:bg-transparent">
                      {headerGroup.headers.map((header) => (
                        <TableHead
                          key={header.id}
                          className="text-[10px] font-bold uppercase tracking-widest py-4 h-auto"
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                        </TableHead>
                      ))}
                    </TableRow>
                  ))}
                </TableHeader>
                <TableBody>
                  {table.getRowModel().rows.map((row) => (
                    <TableRow key={row.id} className="group h-16 transition-colors">
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id} className="py-2">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
