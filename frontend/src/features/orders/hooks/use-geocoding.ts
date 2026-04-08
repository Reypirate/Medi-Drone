import { useState } from 'react';
import { GEOLOCATION_URL } from '../../../lib/api';

export function useGeocoding() {
  const [validation, setValidation] = useState<{
    isLoading: boolean;
    data: any | null;
    error: string | null;
    isConfirmed: boolean;
  }>({
    isLoading: false,
    data: null,
    error: null,
    isConfirmed: false,
  });

  const checkAddress = async (mode: 'postal' | 'coords', values: any) => {
    setValidation(prev => ({ ...prev, isLoading: true, error: null, data: null, isConfirmed: false }));
    let url;
    if (mode === 'postal') {
      const params = new URLSearchParams({ address: values.postalCode + " Singapore", region: "sg" });
      url = `${GEOLOCATION_URL}/maps/api/geocode/json?${params}`;
    } else {
      const params = new URLSearchParams({ lat: values.lat, lng: values.lng });
      url = `${GEOLOCATION_URL}/maps/api/reverse-geocode?${params}`;
    }

    try {
      const resp = await fetch(url);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.error || "Geocoding service error");
      if (!data.customer_coords) throw new Error("Could not resolve this address.");
      
      setValidation(prev => ({ ...prev, isLoading: false, data }));
    } catch (e: any) {
      setValidation(prev => ({ ...prev, isLoading: false, error: e.message }));
    }
  };

  const confirmAddress = () => setValidation(p => ({ ...p, isConfirmed: true }));
  const resetValidation = () => setValidation({ isLoading: false, data: null, error: null, isConfirmed: false });

  return {
    validation,
    checkAddress,
    confirmAddress,
    resetValidation
  };
}
