// vite.config.js
import { defineConfig } from "file:///D:/6th%20Sem%20Project/Final/dbdragoness/dbdragoness/frontend/node_modules/vite/dist/node/index.js";
import react from "file:///D:/6th%20Sem%20Project/Final/dbdragoness/dbdragoness/frontend/node_modules/@vitejs/plugin-react/dist/index.js";
import path from "path";
var __vite_injected_original_dirname = "D:\\6th Sem Project\\Final\\dbdragoness\\dbdragoness\\frontend";
var vite_config_default = defineConfig({
  plugins: [react()],
  base: "/react/",
  build: {
    outDir: path.resolve(__vite_injected_original_dirname, "../static/react"),
    emptyOutDir: true,
    manifest: true
  },
  server: {
    port: 3e3,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJEOlxcXFw2dGggU2VtIFByb2plY3RcXFxcRmluYWxcXFxcZGJkcmFnb25lc3NcXFxcZGJkcmFnb25lc3NcXFxcZnJvbnRlbmRcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIkQ6XFxcXDZ0aCBTZW0gUHJvamVjdFxcXFxGaW5hbFxcXFxkYmRyYWdvbmVzc1xcXFxkYmRyYWdvbmVzc1xcXFxmcm9udGVuZFxcXFx2aXRlLmNvbmZpZy5qc1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vRDovNnRoJTIwU2VtJTIwUHJvamVjdC9GaW5hbC9kYmRyYWdvbmVzcy9kYmRyYWdvbmVzcy9mcm9udGVuZC92aXRlLmNvbmZpZy5qc1wiO2ltcG9ydCB7IGRlZmluZUNvbmZpZyB9IGZyb20gJ3ZpdGUnXG5pbXBvcnQgcmVhY3QgZnJvbSAnQHZpdGVqcy9wbHVnaW4tcmVhY3QnXG5pbXBvcnQgcGF0aCBmcm9tICdwYXRoJ1xuXG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xuICBwbHVnaW5zOiBbcmVhY3QoKV0sXG4gIGJhc2U6ICcvcmVhY3QvJyxcbiAgYnVpbGQ6IHtcbiAgICBvdXREaXI6IHBhdGgucmVzb2x2ZShfX2Rpcm5hbWUsICcuLi9zdGF0aWMvcmVhY3QnKSxcbiAgICBlbXB0eU91dERpcjogdHJ1ZSxcbiAgICBtYW5pZmVzdDogdHJ1ZSxcbiAgfSxcbiAgc2VydmVyOiB7XG4gICAgcG9ydDogMzAwMCxcbiAgICBwcm94eToge1xuICAgICAgJy9hcGknOiB7XG4gICAgICAgIHRhcmdldDogJ2h0dHA6Ly9sb2NhbGhvc3Q6ODAwMCcsXG4gICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcbiAgICAgIH1cbiAgICB9XG4gIH1cbn0pIl0sCiAgIm1hcHBpbmdzIjogIjtBQUE2VyxTQUFTLG9CQUFvQjtBQUMxWSxPQUFPLFdBQVc7QUFDbEIsT0FBTyxVQUFVO0FBRmpCLElBQU0sbUNBQW1DO0FBSXpDLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQzFCLFNBQVMsQ0FBQyxNQUFNLENBQUM7QUFBQSxFQUNqQixNQUFNO0FBQUEsRUFDTixPQUFPO0FBQUEsSUFDTCxRQUFRLEtBQUssUUFBUSxrQ0FBVyxpQkFBaUI7QUFBQSxJQUNqRCxhQUFhO0FBQUEsSUFDYixVQUFVO0FBQUEsRUFDWjtBQUFBLEVBQ0EsUUFBUTtBQUFBLElBQ04sTUFBTTtBQUFBLElBQ04sT0FBTztBQUFBLE1BQ0wsUUFBUTtBQUFBLFFBQ04sUUFBUTtBQUFBLFFBQ1IsY0FBYztBQUFBLE1BQ2hCO0FBQUEsSUFDRjtBQUFBLEVBQ0Y7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
