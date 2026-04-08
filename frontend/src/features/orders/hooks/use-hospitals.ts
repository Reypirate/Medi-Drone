import { useQuery } from '@tanstack/react-query';
import { API_BASE } from '../../../lib/api';

export const useHospitals = () => {
  return useQuery({
    queryKey: ['hospitals'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/inventory/hospitals`);
      if (!res.ok) throw new Error('Failed to fetch hospitals');
      return res.json();
    },
  });
};
