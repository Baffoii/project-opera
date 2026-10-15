/** Minimal pub/sub store. `set` shallow-merges and notifies only on real change. */
export function createStore(initial = {}) {
  let state = Object.freeze({ ...initial });
  const listeners = new Set();
  return {
    get: () => state,
    set(patch) {
      const next = typeof patch === 'function' ? patch(state) : patch;
      const changed = Object.keys(next).filter(
        (key) => !Object.is(state[key], next[key]),
      );
      if (!changed.length) return state;
      const previous = state;
      state = Object.freeze({ ...state, ...next });
      for (const listener of [...listeners]) listener(state, previous, changed);
      return state;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export const initialOperaState = Object.freeze({
  currentImage: null,
  rightsAttested: false,
  status: 'idle',
  error: null,
  analysis: null,
  activeCandidateId: null,
  mode: 'analyze',
  devViewOpen: false,
  model: 'geoclip-v1',
  useVlmClues: true,
  models: [],
  modelsError: null,
  roundTripMs: null,
  panelOpen: true,
});

export function createOperaStore(overrides = {}) {
  return createStore({ ...initialOperaState, ...overrides });
}
