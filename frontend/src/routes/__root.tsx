import { createRootRoute, Outlet } from '@tanstack/react-router';
import { Header } from '../components/Header';

export const Route = createRootRoute({
  component: () => (
    <div className="min-h-screen flex flex-col font-sans transition-colors duration-300">
      <Header />
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  ),
});
