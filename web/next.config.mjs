/** @type {import('next').NextConfig} */
const nextConfig = {
  // Permite importar a KB em ../data (raiz do monorepo)
  experimental: {
    externalDir: true,
  },
};

export default nextConfig;
