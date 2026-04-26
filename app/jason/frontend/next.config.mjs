/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    domains: ["images.metmuseum.org"],
  },
  transpilePackages: ["leaflet", "react-leaflet"],
};

export default nextConfig;
