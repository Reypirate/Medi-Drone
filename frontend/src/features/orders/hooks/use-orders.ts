import { useQuery } from '@tanstack/react-query';
import { API_BASE, DISPATCH_URL } from '../../../lib/api';

export const useActiveMissions = () => {
  return useQuery({
    queryKey: ['missions'],
    queryFn: async () => {
      let res;
      try {
        res = await fetch(`${API_BASE}/api/dispatch/dispatch/missions`); 
      } catch (e) {
        res = await fetch(`${DISPATCH_URL}/dispatch/missions`); 
      }
      if (!res.ok) throw new Error('Failed to fetch active missions');
      return res.json();
    },
    refetchInterval: 5000,
  });
};

export const useOrders = (status?: string) => {
  return useQuery({
    queryKey: ['orders', status],
    queryFn: async () => {
      const url = status 
        ? `${API_BASE}/api/order/orders?status=${status}`
        : `${API_BASE}/api/order/orders`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to fetch orders');
      return res.json();
    },
    refetchInterval: 5000,
  });
};
