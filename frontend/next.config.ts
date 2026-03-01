import type { NextConfig } from "next";

const rawApiUrl = process.env.NEXT_PUBLIC_API_URL;
const apiUrl = rawApiUrl && !rawApiUrl.startsWith("http") ? `https://${rawApiUrl}` : rawApiUrl;

const nextConfig: NextConfig = {
  async rewrites() {
    if (!apiUrl) {
      return [
        {
          source: "/api/:path*",
          destination: "http://localhost:8000/api/:path*",
        },
      ];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
