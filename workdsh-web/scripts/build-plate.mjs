import { build } from 'esbuild';
import { writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const entry = new URL('../packages/plugins/plate/', import.meta.url);
const result = await build({
  entryPoints: [fileURLToPath(new URL('src/client.tsx', entry))],
  bundle: true, write: false, format: 'cjs', platform: 'browser', target: 'es2022',
  external: ['@deepseek-ai/dsh-client-ui-primitives', 'react', 'react/jsx-runtime', 'react-dom', 'react-dom/client'],
});
await writeFile(new URL('dist/client.browser.js', entry), `window.__ModuleLoader__.load({id: "workdsh-plugin-plate", factory: function(require) {\nconst module = { exports: {} };\n${result.outputFiles[0].text}\nreturn module.exports;\n}});\n`);
