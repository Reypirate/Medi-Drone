import { InventoryManager } from '../features/inventory/components/InventoryManager';

export function Inventory() {
  return (
    <div className="max-w-5xl mx-auto p-6 mt-4 flex flex-col gap-6">
      <InventoryManager />
    </div>
  );
}
