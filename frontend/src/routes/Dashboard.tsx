import { useState } from 'react';
import { useOrders } from '../features/orders/hooks/use-orders';
import { useOrderMutations } from '../features/orders/hooks/use-order-mutations';
import { OrderForm } from '../features/orders/components/OrderForm';
import { OrderTable, type Order } from '../features/orders/components/OrderTable';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export function Dashboard() {
  const [tab, setTab] = useState<'active' | 'cancelled' | 'completed'>('active');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);

  const { data: ordersData, isLoading } = useOrders(
    tab === 'active' ? 'PENDING,ASSIGNED,TO_HOSPITAL,TO_CUSTOMER,IN_TRANSIT,IN_FLIGHT,REROUTED_IN_FLIGHT,DISPATCHED' :
    tab === 'cancelled' ? 'UNFULFILLED,CANCELLED' :
    'COMPLETED'
  );

  const { cancelOrder, deleteOrder } = useOrderMutations();

  const handleCancelClick = (id: string) => {
    setPendingActionId(id);
    setCancelDialogOpen(true);
  };

  const handleDeleteClick = (id: string) => {
    setPendingActionId(id);
    setDeleteDialogOpen(true);
  };

  return (
    <div className="container max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-[440px_1fr] gap-6">
      {/* Left Column: Log and Form */}
      <div className="flex flex-col gap-6">
        <Card className="shadow-lg border-primary/10">
          <OrderForm onSuccess={() => setTab('active')} />
        </Card>

        {/* System Logs Area */}
        <Card className="border-slate-800 bg-slate-900/50">
          <CardHeader className="py-3 border-b border-slate-800">
            <CardTitle className="text-[11px] font-bold uppercase tracking-widest text-slate-400 font-mono">Environment Logs</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="h-40 overflow-y-auto p-3 font-mono text-[10px] leading-relaxed text-slate-300">
              <div className="flex gap-2 mb-1">
                <span className="text-primary font-bold">[SYSTEM]</span>
                <span>Initializing telemetry relay...</span>
              </div>
              <div className="flex gap-2 mb-1">
                <span className="text-green-500 font-bold">[GATEWAY]</span>
                <span>Connected to Kong API Gateway at localhost:8000</span>
              </div>
              <div className="flex gap-2 mb-1">
                <span className="text-yellow-500 font-bold">[WARN]</span>
                <span>Weather module reporting high humidity in sector 4.</span>
              </div>
              <div className="flex gap-2 mb-1">
                <span className="text-primary font-bold">[SYSTEM]</span>
                <span>Dashboard synchronized with RabbitMQ dispatch bus.</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* SMS Notifications Logs */}
        <Card className="border-slate-800 bg-slate-900/50">
          <CardHeader className="py-3 border-b border-slate-800">
            <CardTitle className="text-[11px] font-bold uppercase tracking-widest text-slate-400 font-mono">SMS Notification Bus</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="h-32 overflow-y-auto p-3 font-mono text-[10px] leading-relaxed text-slate-400 italic">
              <div className="mb-2 pb-1 border-b border-white/5">
                <div className="text-[9px] text-slate-500 not-italic mb-0.5">09:47:00 | +65 **** 1234</div>
                "Medi-Drone: Order #4d9e initialized. Drone Alpha-7 dispatched to your location. ETA: 4min."
              </div>
              <div className="text-[9px] text-center opacity-40 py-4 not-italic">Listening for outgoing SMS triggers...</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Right Column: Mission Control */}
      <div className="flex flex-col gap-6">
        <Card className="min-h-[500px] border-primary/5 shadow-md">
          <CardHeader className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b pb-4 bg-muted/20">
            <div>
              <CardTitle className="text-lg">Mission Control Center</CardTitle>
              <CardDescription className="text-xs">Real-time status of active and legacy flight deployments</CardDescription>
            </div>
            
            <Tabs value={tab} onValueChange={(v: string) => setTab(v as any)} className="bg-background rounded-md p-1 border">
              <TabsList className="h-8 bg-transparent">
                <TabsTrigger value="active" className="text-[11px] h-6 px-3">Active</TabsTrigger>
                <TabsTrigger value="completed" className="text-[11px] h-6 px-3">History</TabsTrigger>
                <TabsTrigger value="cancelled" className="text-[11px] h-6 px-3">Aborted</TabsTrigger>
              </TabsList>
            </Tabs>
          </CardHeader>

          <CardContent className="pt-6">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
                <div className="w-10 h-10 border-4 border-primary/30 border-t-primary rounded-full animate-spin" />
                <span className="text-sm font-medium">Fetching satellite telemetry...</span>
              </div>
            ) : !ordersData?.orders || ordersData.orders.length === 0 ? (
              <div className="text-center py-24 text-muted-foreground bg-muted/10 rounded-xl border-2 border-dashed border-muted">
                <div className="text-4xl mb-3 opacity-20">📡</div>
                <div className="text-sm font-semibold">Zero records found</div>
                <div className="text-xs max-w-[200px] mx-auto mt-1 opacity-60">No flight logs matching this category are available at this time.</div>
              </div>
            ) : (
              <OrderTable 
                data={ordersData.orders as Order[]} 
                tab={tab} 
                onCancel={handleCancelClick}
                onDelete={handleDeleteClick}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Confirmation Dialogs */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Permanent Deletion</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete order <strong>{pendingActionId}</strong>? This will remove the record from all mission history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Discard</AlertDialogCancel>
            <AlertDialogAction 
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => pendingActionId && deleteOrder.mutate(pendingActionId)}
            >
              Delete Permanently
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Abort Mission</AlertDialogTitle>
            <AlertDialogDescription>
              This will immediately recall the drone for order <strong>{pendingActionId}</strong>. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep Active</AlertDialogCancel>
            <AlertDialogAction 
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => pendingActionId && cancelOrder.mutate(pendingActionId)}
            >
              Abort Mission
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
