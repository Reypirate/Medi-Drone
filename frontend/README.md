# 🛸 Medi-Drone Fleet Command

A command center for autonomous medical drone delivery operations. Built with a focus on real-time telemetry, type safety, and premium aesthetics.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![React](https://img.shields.io/badge/React-19-blue?logo=react)
![Bun](https://img.shields.io/badge/Bun-Runtime-black?logo=bun)
![Tailwind](https://img.shields.io/badge/Tailwind-CSS-38B2AC?logo=tailwind-css)

## ✨ Features

- **📍 Live Mission Tracking**: Real-time Google Maps integration with mission paths, drone telemetry, and hazard zone overlays.
- **🔋 Fleet Management**: Comprehensive dashboard for monitoring drone battery health, flight status, and automated maintenance triggers.
- **🚑 Emergency Ordering**: Robust request system with integrated address geocoding and type-safe validation using **TanStack Form** and **Zod**.
- **⛈️ Simulation Suite**: Advanced controls for triggering micro-burst weather events, hazard zones, and flight rerouting logic.
- **📦 Inventory Insights**: Real-time visibility into medical stock across the delivery network.
- **🌓 Adaptive Theme**: High-contrast Dark/Light mode support managed via `next-themes`.

## 🛠️ Tech Stack

- **Core**: [React 19](https://react.dev/), [TypeScript](https://www.typescriptlang.org/)
- **State & Routing**: [TanStack Router](https://tanstack.com/router), [Query](https://tanstack.com/query), [Table](https://tanstack.com/table), [Form](https://tanstack.com/form)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/) with Glassmorphism and Lucide Icons
- **Server**: [Hono](https://hono.dev/) with Bun integration for ultra-fast static serving
- **Validation**: [Zod](https://zod.dev/) & [@t3-oss/env-core](https://env.t3.gg/)
- **Infrastructure**: [Bun](https://bun.sh/), [Docker](https://www.docker.com/)

## 🚀 Getting Started

### Prerequisites

- [Bun](https://bun.sh/) (Recommended) or [Node.js](https://nodejs.org/)
- [pnpm](https://pnpm.io/)
- A Google Maps API Key with **Maps JavaScript API** enabled.

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/medi-drone.git
   cd medi-drone/frontend
   ```

2. Install dependencies:
   ```bash
   pnpm install
   ```

3. Configure Environment Variables:
   Create a `.env` file in the root of the `/frontend` directory:
   ```env
   VITE_GOOGLE_MAPS_API_KEY=your_api_key_here
   ```

## 📖 Development Scripts

| Command                 | Description                                                              |
| :---------------------- | :----------------------------------------------------------------------- |
| `pnpm run dev`          | Starts the Vite development server on port 8080.                         |
| `pnpm run build`        | Builds the frontend and bundles the Hono server into `/build`.           |
| `pnpm run start`        | Serves the production bundle using the Bun-based Hono server.            |
| `pnpm run build:docker` | Builds the production assets and packages them into a slim Docker image. |
| `pnpm run lint`         | Performs a fast lint pass using Oxlint.                                  |

## 🐳 Dockerization

The application is optimized for containerization using a minimal runner image.

**Build and Run:**
```bash
# Build the image
pnpm run build:docker

# Run the container
docker run -p 8080:8080 medi-drone-frontend
```

## 📂 Project Structure

```text
frontend/
├── build/             # Production artifacts & bundled server
├── server/            # Hono server for static distribution
│   ├── env.ts         # Server-side env validation
│   └── index.ts       # Server entry point
├── src/
│   ├── features/      # Domain-specific logic (fleet, orders, simulation)
│   ├── providers/     # React Context & Providers (Query, Theme)
│   ├── routes/        # Page components and views
│   └── env.ts         # Client-side env validation
├── tsconfig.json      # Consolidated TypeScript configuration
└── Dockerfile         # Slim production runner
```

## 📄 License

This project is licensed under the MIT License.
