import {
  createRouter,
  createRoute,
  createRootRoute,
  Outlet,
} from '@tanstack/react-router';
import { Header } from './components/Header';
import { Dashboard } from './routes/Dashboard';
import { Inventory } from './routes/Inventory';
import { Drones } from './routes/Drones';
import { Simulation } from './routes/Simulation';
import LiveMap from './routes/LiveMap';

const rootRoute = createRootRoute({
  component: () => (
    <div className="min-h-screen flex flex-col font-sans transition-colors duration-300">
      <Header />
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: Dashboard,
});

const inventoryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/inventory',
  component: Inventory,
});

const dronesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/drones',
  component: Drones,
});

const simulationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/simulation',
  component: Simulation,
});

const liveMapRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/livemap',
  component: LiveMap,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  inventoryRoute,
  dronesRoute,
  simulationRoute,
  liveMapRoute,
]);

export const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
