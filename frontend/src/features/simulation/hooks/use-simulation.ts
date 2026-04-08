import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { WEATHER_URL, DISPATCH_URL } from '../../../lib/api';
import { useState } from 'react';

export const useSimulationStatus = () => {
  return useQuery({
    queryKey: ['simulation-status'],
    queryFn: async () => {
      const res = await fetch(`${WEATHER_URL}/api/weather/simulate/status`);
      if (!res.ok) throw new Error('Failed to fetch simulation status');
      return res.json();
    },
    refetchInterval: 10000,
  });
};

export function useSimulationMutations() {
  const queryClient = useQueryClient();
  const [logs, setLogs] = useState<{msg: string, time: string, type: 'info'|'warn'|'err'}[]>([]);

  const addLog = (msg: string, type: 'info'|'warn'|'err' = 'info') => {
    setLogs(prev => [{ msg, time: new Date().toLocaleTimeString(), type }, ...prev].slice(0, 50));
  };

  const disableMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${WEATHER_URL}/api/weather/simulate/disable`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to disable simulation');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['simulation-status'] });
      addLog("Global simulation disabled. Returning to real-time telemetry.", "info");
    },
  });

  const activateSimulation = useMutation({
    mutationFn: async (payload: any) => {
      const res = await fetch(`${WEATHER_URL}/api/weather/simulate/enable`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed to activate simulation');
      return res.json();
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['simulation-status'] });
      if (variables.force_unsafe) {
         addLog("MODE 1 (Cancellation) Activated: Stress testing order abort logic.", "warn");
      } else {
         addLog(`MODE 2 (Rerouting) Activated: ${variables.hazard_zones.length} hazard sites injected.`, "warn");
      }
    },
  });

  const fastForwardMutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      const res = await fetch(`${WEATHER_URL}/api/weather/simulate/fast-forward`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled, multiplier: 4 })
      });
      if (!res.ok) throw new Error('Fast Forward failed');
      return res.json();
    },
    onSuccess: (_, enabled) => {
      addLog(`Simulation speed: ${enabled ? '4x HIGH SPEED' : '1x REALTIME'}`, "info");
      queryClient.invalidateQueries({ queryKey: ['simulation-status'] });
    }
  });

  const emergencyResetMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${DISPATCH_URL}/dispatch/reset`, { method: 'POST' });
      if (!res.ok) throw new Error('Reset failed');
      return res.json();
    },
    onSuccess: () => {
      addLog("EMERGENCY RESET: All flight plans purged. Fleet returning to depot.", "err");
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['inventory'] });
      queryClient.invalidateQueries({ queryKey: ['drones'] });
    }
  });

  const triggerPollMutation = useMutation({
    mutationFn: async (orderId: string) => {
        const res = await fetch(`${DISPATCH_URL}/dispatch/order/${orderId}/poll-weather`, { method: 'POST' });
        if (!res.ok) throw new Error('Poll failed');
        return res.json();
    },
    onSuccess: (_, id) => addLog(`Forced weather poll for order ${id.substring(0,8)}`, "info")
  });

  return {
    logs,
    addLog,
    disableMutation,
    activateSimulation,
    fastForwardMutation,
    emergencyResetMutation,
    triggerPollMutation
  };
}
