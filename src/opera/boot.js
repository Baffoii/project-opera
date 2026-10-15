import './opera.css';
import { createCandidateOverlays } from './globe/candidateOverlays.js';
import { mountOpera } from './app.js';

const POLL_MS = 250;
const GIVE_UP_MS = 120_000;

// Upstream publishes its live viewer on window.__godsEyeView once the scene is up.
function whenViewerReady() {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const tick = () => {
      const handle = window.__godsEyeView;
      if (handle?.viewer) return resolve(handle);
      if (Date.now() - started > GIVE_UP_MS)
        return reject(new Error('OPERA: globe viewer never became ready'));
      setTimeout(tick, POLL_MS);
    };
    tick();
  });
}

whenViewerReady()
  .then(({ viewer, requestRender }) => {
    const overlays = createCandidateOverlays(viewer, { requestRender });
    const opera = mountOpera({ overlays });
    window.__opera = opera;
  })
  .catch((error) => console.warn(error.message));
