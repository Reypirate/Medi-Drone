import { useMutation, useQueryClient } from '@tanstack/react-query';
import { API_BASE } from '../../../lib/api';

export function useOrderMutations() {
  const queryClient = useQueryClient();

  const submitOrder = useMutation({
    mutationFn: async (payload: any) => {
      const res = await fetch(`${API_BASE}/api/order/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.reason || errorData.error || 'Failed to submit order');
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['inventory'] });
    },
  });

  const cancelOrder = useMutation({
    mutationFn: async (orderId: string) => {
      const res = await fetch(`${API_BASE}/api/order/order/${orderId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: "USER_REQUEST" })
      });
      if (!res.ok) throw new Error('Cancel failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    }
  });

  const deleteOrder = useMutation({
    mutationFn: async (orderId: string) => {
      const res = await fetch(`${API_BASE}/api/order/order/${orderId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    }
  });

  return {
    submitOrder,
    cancelOrder,
    deleteOrder,
  };
}
