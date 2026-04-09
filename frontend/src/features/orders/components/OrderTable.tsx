import { useMemo } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table';
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Ban, Trash2 } from 'lucide-react';

export type Order = {
  order_id: string;
  item_id: string;
  quantity: number;
  customer_address: string;
  status: string;
  hospital_name?: string;
  hospital_id?: string;
  urgency_level?: string;
  drone_id?: string;
  eta_minutes?: number;
  dispatch_status?: string;
  cancel_message?: string;
};

const columnHelper = createColumnHelper<Order>();

interface OrderTableProps {
  data: Order[];
  tab: 'active' | 'cancelled' | 'completed';
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
}

export function OrderTable({ data, tab, onCancel, onDelete }: OrderTableProps) {
  const columns = useMemo(
    () => [
      columnHelper.accessor('order_id', {
        header: 'Order ID',
        cell: (info) => <div className="font-mono text-[11px] font-bold truncate max-w-[80px]">{info.getValue()}</div>,
      }),
      columnHelper.accessor('item_id', {
        header: 'Item',
        cell: (info) => (
          <div className="flex flex-col">
            <span className="font-medium">{info.getValue()}</span>
            <span className="text-[10px] text-muted-foreground">{info.row.original.hospital_name || 'Auto-select'}</span>
          </div>
        )
      }),
      columnHelper.accessor('status', {
        header: 'Status',
        cell: (info) => {
          const status = info.getValue() as string;
          let variant: 'default' | 'secondary' | 'destructive' | 'outline' = 'outline';
          
          if (status === 'COMPLETED' || status === 'DELIVERED') variant = 'default';
          else if (['IN_TRANSIT', 'IN_FLIGHT', 'TO_HOSPITAL', 'TO_CUSTOMER'].includes(status)) variant = 'secondary';
          else if (status.includes('REROUTE')) variant = 'secondary';
          else if (status === 'UNFULFILLED' || status.includes('CANCEL') || status.includes('FAIL')) variant = 'destructive';

          return (
            <div className="flex flex-col gap-1">
              <Badge variant={variant} className="text-[9px] py-0 px-1.5 h-4 rounded-sm uppercase tracking-tight w-fit">
                {status.replace(/_/g, ' ')}
              </Badge>
              {info.row.original.drone_id && (
                <span className="text-[10px] text-muted-foreground">Drone: {info.row.original.drone_id}</span>
              )}
            </div>
          );
        },
      }),
      columnHelper.display({
        id: 'actions',
        header: 'Actions',
        cell: (info) => {
          const order = info.row.original;
          const isActive = tab === 'active';
          
          return (
            <div className="flex gap-1">
              {isActive ? (
                   <Button 
                    variant="ghost" 
                    size="icon" 
                    className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={() => onCancel(order.order_id)}
                   >
                     <Ban className="h-3.5 w-3.5" />
                   </Button>
              ) : (
                <Button 
                  variant="ghost" 
                  size="icon" 
                  className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  onClick={() => onDelete(order.order_id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          );
        }
      })
    ],
    [tab, onCancel, onDelete]
  );

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="rounded-xl border overflow-hidden">
      <Table>
        <TableHeader className="bg-muted/50">
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="hover:bg-transparent border-none">
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id} className="text-[10px] font-bold uppercase tracking-widest h-10">
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id} className="group transition-colors h-14">
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id} className="py-2 text-[12px]">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
