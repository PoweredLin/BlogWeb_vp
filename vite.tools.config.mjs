import {defineConfig} from 'vite';
import path from 'node:path';
export default defineConfig({
  root:path.resolve('source/tools'),base:'/tools-app/',publicDir:false,
  build:{outDir:path.resolve('public/tools-app'),emptyOutDir:true},
});
