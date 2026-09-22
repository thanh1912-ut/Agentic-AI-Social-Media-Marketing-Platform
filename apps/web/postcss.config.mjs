/**
 * Tailwind CSS v4 dùng cấu hình CSS-first: không có `tailwind.config.ts`.
 * Mọi token khai báo trong `src/app/globals.css` qua `@theme`.
 */
const config = {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};

export default config;
