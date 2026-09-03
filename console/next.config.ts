import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The widget renders inside an iframe on the demo site, where the dev indicator badge
  // lands on top of the call button. Nothing to see there anyway.
  devIndicators: false,

  // Same-origin proxy to FastAPI. Matters more here than on the demo site: the console
  // session cookie is HttpOnly and same-site, so it must not cross an origin boundary.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/:path*` }];
  },
};

export default nextConfig;
