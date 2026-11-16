import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // ECS image (Dockerfile): a self-contained server.js with only the node_modules it needs.
  output: "standalone",
  poweredByHeader: false,
  // The interface runs with `next dev` for the demo and the video: keep the route badge off the
  // journey's corners (compile and runtime errors are still shown).
  devIndicators: false,
  // The AWS SDK clients are only used by the server-side gateway; keep them out of the bundle.
  serverExternalPackages: [
    "@aws-sdk/client-bedrock-agentcore",
    "@aws-sdk/client-bedrock-agentcore-control",
    "@aws-sdk/client-sfn",
  ],
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
