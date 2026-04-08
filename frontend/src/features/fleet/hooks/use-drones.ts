import { useQuery } from '@tanstack/react-query';
import { API_BASE } from '../../../lib/api';

export const useDrones = () => {
  return useQuery({
    queryKey: ['drones'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/drones/drones`);
      if (!res.ok) throw new Error('Failed to fetch drones');
      return res.json();
    },
    refetchInterval: 5000,
  });
};
