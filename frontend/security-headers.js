// Security headers for the frontend (findings from the OWASP ZAP DAST scan, see SECURITY.md).
// Used by `vite preview` locally; vercel.json sets the same headers in production.
// Keep the two in sync.
export const securityHeaders = {
  // Only load scripts, styles and data from this site; API calls only to the backend.
  "Content-Security-Policy": [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'", // stylesheets only from this site; no injected <style> blocks
    "style-src-attr 'unsafe-inline'", // React and Recharts set inline style="" attributes (e.g. bar widths)
    "img-src 'self' data:",
    "connect-src 'self' http://localhost:8000 https://*.onrender.com",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; "),
  "X-Frame-Options": "DENY", // anti-clickjacking for older browsers (ZAP 10020)
  "X-Content-Type-Options": "nosniff", // (ZAP 10021)
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  // Cross-origin isolation against Spectre-style side channels (ZAP 90004).
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
  "Cross-Origin-Resource-Policy": "same-origin",
};
