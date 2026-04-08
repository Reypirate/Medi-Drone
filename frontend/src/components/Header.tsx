import { Link } from '@tanstack/react-router';
import { useTheme } from '../providers/ThemeProvider';
import { Moon, Sun } from 'lucide-react';
import { Button, buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useActiveMissions } from '../features/orders/hooks/use-orders';

export function Header() {
  const { theme, setTheme } = useTheme();
  const { data: missionsData } = useActiveMissions();
  const activeMissionsCount = missionsData?.active_missions?.length || 0;

  return (
    <header className="bg-gradient-to-br from-slate-800 to-slate-900 border-b border-slate-700 px-8 py-4 flex items-center justify-between">
      <div className="flex items-center gap-3 text-[22px] font-bold text-slate-50">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center overflow-hidden bg-slate-800">
          <img src="/medi-drone-logo.png" alt="Medi-Drone" className="w-full h-full object-cover" />
        </div>
        Medi-Drone
      </div>

      <div className="flex gap-1 bg-slate-900 rounded-lg p-1">
        {[
          { path: '/', label: 'Dashboard' },
          { path: '/inventory', label: 'Inventory' },
          { path: '/drones', label: 'Drones' },
          { path: '/simulation', label: 'Simulation' },
          { path: '/livemap', label: 'Live Map' },
        ].map((nav) => (
            <Link
              key={nav.path}
              to={nav.path}
              className={cn(
                buttonVariants({ variant: 'ghost' }),
                "text-slate-400 hover:text-slate-200 hover:bg-slate-800 [&.active]:bg-slate-700 [&.active]:text-slate-50"
              )}
            >
                {nav.label}
            </Link>
        ))}
      </div>

      <div className="flex gap-5 text-sm text-slate-400 items-center">
        <div className="flex items-center">
          <span className="inline-block w-2 h-2 rounded-full mr-1.5 bg-green-500"></span>
          API Gateway
        </div>
        <div className="flex items-center">
          <span className="inline-block w-2 h-2 rounded-full mr-1.5 bg-green-500"></span>
          RabbitMQ
        </div>
        <div>{activeMissionsCount} active missions</div>
        
        <Button 
          variant="outline"
          size="icon"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="ml-4 border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300"
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>
    </header>
  );
}
