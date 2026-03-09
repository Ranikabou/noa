/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@noa/ui', '@noa/contracts'],
};

module.exports = nextConfig;
