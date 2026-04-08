import { useMemo, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table';
import { Search, RefreshCw, Package, MapPin, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useInventory, useInventoryMutations, useInventoryItems } from '../hooks/use-inventory';

type InventoryItem = {
  hospital_id: string;
  item_id: string;
  quantity: number;
};

const columnHelper = createColumnHelper<InventoryItem>();

export function InventoryManager() {
  const [selectedItem, setSelectedItem] = useState<string>('');
  const { data: inventory, isLoading } = useInventory(selectedItem || undefined);
  const { data: itemList, isLoading: itemsLoading } = useInventoryItems();
  const { restockMutation } = useInventoryMutations();

  const totalStock = useMemo(() => {
    if (!inventory) return 0;
    return inventory.reduce((acc: number, curr: any) => acc + curr.quantity, 0);
  }, [inventory]);

  const columns = useMemo(
    () => [
      columnHelper.accessor('hospital_id', {
        header: 'Hospital Location',
        cell: (info) => (
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-muted rounded">
              <MapPin className="h-3 w-3 text-muted-foreground" />
            </div>
            <div className="flex flex-col">
              <span className="font-bold text-[13px]">{info.getValue()}</span>
              <span className="text-[10px] text-muted-foreground">Singapore District Relay</span>
            </div>
          </div>
        ),
      }),
      columnHelper.accessor('quantity', {
        header: 'Available Stock',
        cell: (info) => {
          const qty = info.getValue() as number;
          let variant: 'default' | 'secondary' | 'destructive' | 'outline' = 'destructive';
          if (qty >= 30) { variant = 'default'; }
          else if (qty >= 10) { variant = 'secondary'; }
          
          return (
            <div className="flex items-center gap-2">
              <Badge variant={variant} className={`text-[11px] font-mono h-5 px-2 ${qty >= 30 ? 'bg-green-500/10 text-green-500 border-green-500/20' : ''}`}>
                {qty} UNITS
              </Badge>
              {qty < 10 && <AlertCircle className="h-3 w-3 text-destructive animate-pulse" />}
            </div>
          );
        },
      }),
    ],
    []
  );

  const table = useReactTable({
    data: inventory || [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <>
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Medical Inventory</h1>
          <p className="text-muted-foreground text-sm">Monitor and manage critical medical supply levels across the hospital network.</p>
        </div>
        <Button
          onClick={() => restockMutation.mutate()}
          disabled={restockMutation.isPending}
          className="shadow-sm"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${restockMutation.isPending ? 'animate-spin' : ''}`} />
          {restockMutation.isPending ? 'Restocking Hubs...' : 'Restock All Hubs'}
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="md:col-span-2 border-primary/5 shadow-md">
          <CardHeader className="pb-3 border-b bg-muted/20">
            <CardTitle className="text-base flex items-center gap-2">
              <Search className="h-4 w-4 text-primary" />
              Stock Availability Lookup
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="mb-6 flex gap-4">
              <div className="flex-1">
                <Select value={selectedItem === '' ? 'all' : selectedItem} onValueChange={(val) => setSelectedItem(val === 'all' || !val ? '' : val)}>
                  <SelectTrigger className="h-10">
                    <SelectValue placeholder={itemsLoading ? "Loading inventory items..." : "-- Select Medical Item --"} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">-- Show All Items --</SelectItem>
                    {itemList?.map((item: any) => (
                      <SelectItem key={item.item_id} value={item.item_id}>
                        {item.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {!selectedItem ? (
              <div className="flex flex-col items-center justify-center py-20 text-muted-foreground bg-muted/20 border-2 border-dashed rounded-xl">
                <Package className="h-10 w-10 mb-2 opacity-20" />
                <p className="text-sm font-medium">Select an item above to query network stock</p>
              </div>
            ) : isLoading ? (
              <div className="flex items-center justify-center py-20 gap-3 text-muted-foreground">
                <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
                <span className="text-sm">Querying database...</span>
              </div>
            ) : (
              <div className="rounded-xl border overflow-hidden">
                <Table>
                  <TableHeader className="bg-muted/50">
                    {table.getHeaderGroups().map((headerGroup) => (
                      <TableRow key={headerGroup.id}>
                        {headerGroup.headers.map((header) => (
                          <TableHead
                            key={header.id}
                            className="text-[11px] font-bold uppercase tracking-wider h-10"
                          >
                            {header.isPlaceholder
                              ? null
                              : flexRender(header.column.columnDef.header, header.getContext())}
                          </TableHead>
                        ))}
                      </TableRow>
                    ))}
                  </TableHeader>
                  <TableBody>
                    {table.getRowModel().rows.map((row) => (
                      <TableRow key={row.id}>
                        {row.getVisibleCells().map((cell) => (
                          <TableCell key={cell.id} className="py-2.5">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                    {table.getRowModel().rows.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={2} className="h-32 text-center text-muted-foreground text-sm italic">
                          No hospital records found for {selectedItem}.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-6">
          <Card className="bg-primary/5 border-primary/10 shadow-sm">
            <CardHeader className="pb-2">
              <CardDescription className="text-xs uppercase font-bold tracking-widest">Network Summary</CardDescription>
              <CardTitle className="text-3xl font-black">{totalStock} UNITS</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-[11px] text-muted-foreground leading-snug">
                Total available stockpile for <span className="text-primary font-bold">{selectedItem || 'All Items'}</span> across 3 core hospitals.
              </p>
            </CardContent>
          </Card>

          <Card className="border-slate-800 bg-slate-900 shadow-xl overflow-hidden">
            <CardHeader className="p-4 border-b border-slate-800">
               <CardTitle className="text-[11px] font-mono font-bold tracking-[.2em] uppercase text-slate-500">Logistics Status</CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
               {[
                 { label: "Central Hub", status: "Nominal", value: "98.2%", color: "text-green-500" },
                 { label: "Dispatch Bus", status: "Active", value: "14ms", color: "text-primary" },
                 { label: "Encryption", status: "TLS 1.3", value: "AES-256", color: "text-slate-400" }
               ].map(stat => (
                 <div key={stat.label} className="flex justify-between items-center text-[11px]">
                   <span className="text-slate-400 font-mono">{stat.label}</span>
                   <div className="flex items-center gap-2">
                     <span className="text-slate-600 italic">[{stat.status}]</span>
                     <span className={`font-bold ${stat.color}`}>{stat.value}</span>
                   </div>
                 </div>
               ))}
               <div className="pt-3 border-t border-slate-800 mt-2">
                  <Badge variant="outline" className="w-full justify-center bg-slate-800/50 text-[10px] text-slate-500 border-slate-700 py-1 font-mono">
                    LAST SYNC: {new Date().toLocaleTimeString()}
                  </Badge>
               </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
