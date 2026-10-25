import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { securityHeaders } from "./security-headers.js";

export default defineConfig({
  plugins: [react()],
  preview: {
    headers: securityHeaders,
  },
});
