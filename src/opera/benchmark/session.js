export const initialBenchmarkState = Object.freeze({
  phase: 'setup', // setup | loading | guessing | revealing | revealed | finished
  datasets: null,
  datasetsError: null,
  dataset: null,
  split: 'heldout',
  n: 5,
  rounds: [],
  index: 0,
  imageUrl: null,
  guess: null,
  result: null,
  results: [],
  error: null,
});

const median = (values) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};
const mean = (values) =>
  values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;

/**
 * Aggregate finished rounds. A round the player skipped is not counted for the player; a round where the
 * model abstained scores 0 for the model (it declined to answer) but is reported separately.
 */
export function summarizeSession(results = []) {
  const guessed = results.filter((r) => r.user);
  const userErrors = guessed.map((r) => r.user.error_km);
  const answered = results.filter((r) => r.model?.status === 'complete');
  const modelErrors = answered.map((r) => r.model.top1_error_km);
  return {
    rounds: results.length,
    user: {
      played: guessed.length,
      totalScore: guessed.reduce((s, r) => s + r.user.score, 0),
      medianKm: median(userErrors),
      meanKm: mean(userErrors),
    },
    model: {
      answered: answered.length,
      abstained: results.filter((r) => r.model?.status === 'abstained').length,
      unavailable: results.filter(
        (r) => r.model && !['complete', 'abstained'].includes(r.model.status),
      ).length,
      totalScore: answered.reduce((s, r) => s + (r.model.score ?? 0), 0),
      medianKm: median(modelErrors),
      meanKm: mean(modelErrors),
    },
  };
}
