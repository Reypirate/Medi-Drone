import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { API_BASE } from '../../../lib/api';

export const useInventory = (itemId?: string) => {
  return useQuery({
    queryKey: ['inventory', itemId],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/inventory/inventory`);
      if (!res.ok) throw new Error('Failed to fetch inventory');
      const data = await res.json();
      const rows = Array.isArray(data) ? data : data.inventory || [];
      return itemId ? rows.filter((r: any) => r.item_id === itemId) : rows;
    },
  });
};

export function useInventoryMutations() {
  const queryClient = useQueryClient();

  const restockMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/api/inventory/inventory/restock`, { method: 'POST' });
      if (!res.ok) throw new Error('Restock failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] });
    },
  });

  return {
    restockMutation
  };
}
