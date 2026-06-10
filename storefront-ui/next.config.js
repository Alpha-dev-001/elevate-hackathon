/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Alibaba Cloud Function Compute compatible output
  output: 'standalone',
  experimental: {
    serverComponentsExternalPackages: ['ioredis', 'qrcode'],
  },
  env: {
    NEXT_PUBLIC_APP_NAME: 'Elevate',
    NEXT_PUBLIC_APP_VERSION: '1.0.0',
  },
}

module.exports = nextConfig
