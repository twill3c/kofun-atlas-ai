/** @type {import('next').NextConfig} */
const nextConfig = {
  // 完全な静的書き出し。serverless function をひとつも作らない(構想書 §35 / §36.2)。
  // /api/health は force-static なので書き出し時に JSON として焼かれる。
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
