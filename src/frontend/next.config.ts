import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/assets/:path*",
        destination: `${backendUrl}/assets/:path*`,
      },
    ];
  },
};

export default nextConfig;
