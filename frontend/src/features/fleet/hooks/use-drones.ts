import { useQuery } from '@tanstack/react-query';
import { FLEET_URL } from '../../../lib/api';

export const useDrones = () => {
  return useQuery({
    queryKey: ['drones'],
    queryFn: async () => {
      const res = await fetch(`${FLEET_URL}/drones`);
      if (!res.ok) throw new Error('Failed to fetch drones');
      return res.json();
    },
    refetchInterval: 5000,
  });
};
