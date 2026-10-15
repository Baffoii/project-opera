import { describe, expect, it, vi } from 'vitest';
import { createOperaStore, createStore } from '../../src/opera/state/store.js';

describe('store', () => {
  it('starts with the documented OPERA state', () => {
    const s = createOperaStore().get();
    expect(s).toMatchObject({
      currentImage: null,
      analysis: null,
      activeCandidateId: null,
      mode: 'analyze',
      devViewOpen: false,
    });
  });
  it('notifies subscribers with changed keys, and only on real change', () => {
    const store = createStore({ a: 1, b: 2 });
    const fn = vi.fn();
    store.subscribe(fn);
    store.set({ a: 1 });
    expect(fn).not.toHaveBeenCalled();
    store.set({ a: 5 });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn.mock.calls[0][2]).toEqual(['a']);
    expect(store.get()).toEqual({ a: 5, b: 2 });
  });
  it('supports updater functions and unsubscribe', () => {
    const store = createStore({ n: 1 });
    const fn = vi.fn();
    const off = store.subscribe(fn);
    store.set((s) => ({ n: s.n + 1 }));
    off();
    store.set({ n: 10 });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(store.get().n).toBe(10);
  });
  it('state is frozen', () => {
    const store = createStore({ a: 1 });
    expect(() => {
      'use strict';
      store.get().a = 2;
    }).toThrow();
  });
});
