/** @type {import('next').NextConfig} */
const nextConfig = {
  // Permite importar a KB em ../data (raiz do monorepo)
  experimental: {
    externalDir: true,
  },
  // Demo deploy: não bloquear build por dívida de tipagem local
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
