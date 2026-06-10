import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'standalone',
  // Proxy all /api/* requests in dev to the FastAPI backend (port 8100 inside Docker, 8100 on NAS Tailscale).
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8100';
    return [
      { source: '/api/:path*', destination: `${backend}/api/:path*` },
      { source: '/auth/:path*', destination: `${backend}/auth/:path*` },
    ];
  },
};

export default nextConfig;
