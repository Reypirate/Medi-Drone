import { useQuery } from '@tanstack/react-query';
import { HOSPITAL_URL } from '../../../lib/api';

export const useHospitals = () => {
  return useQuery({
    queryKey: ['hospitals'],
    queryFn: async () => {
      // HOSPITAL_URL is already '/api/hospital'
      const res = await fetch(`${HOSPITAL_URL}/hospitals`);
      if (!res.ok) throw new Error('Failed to fetch hospitals');
      const data = await res.json();
      // Handle both direct array and { hospitals: [...] } wrapper
      return Array.isArray(data) ? data : data.hospitals || [];
    },
  });
};
