/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Vercel handles standalone output natively; this is also FC-compatible.
  output: 'standalone',
  images: {
    // Allow product images from Alibaba Cloud OSS and any merchant-provided URLs.
    remotePatterns: [
      { protocol: 'https', hostname: '**.aliyuncs.com' },
      { protocol: 'https', hostname: '**.alicdn.com' },
    ],
  },
  env: {
    NEXT_PUBLIC_APP_NAME: 'Elevate',
    NEXT_PUBLIC_APP_VERSION: '1.0.0',
  },
}

module.exports = nextConfig
