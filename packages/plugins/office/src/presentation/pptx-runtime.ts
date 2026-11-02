/**
 * On-demand PPTX editor runtime. Bundled as `client.office-pptx.js` so the
 * ~17 MB presentation stack stays out of the boot bundle.
 */
export { mountNativePpt } from './frame.js';
export { mountPptx } from './native-react/editor.js';
