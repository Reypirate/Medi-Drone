import { useQuery } from '@tanstack/react-query';
import { DISPATCH_URL, ORDERS_LIST_URL } from '../../../lib/api';

export const useActiveMissions = () => {
  return useQuery({
    queryKey: ['missions'],
    queryFn: async () => {
      const res = await fetch(`${DISPATCH_URL}/dispatch/missions`); 
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
        ? `${ORDERS_LIST_URL}/orders?status=${status}`
        : `${ORDERS_LIST_URL}/orders`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to fetch orders');
      return res.json();
    },
    refetchInterval: 5000,
  });
};
