# GeoCLIP on `opera-commons-v1`: first evaluation (2026-10-15)

**Read this first.** 59 photos is far too few to support any accuracy claim. These numbers show that the evaluation
pipeline works and give a rough feel; they are not a measurement of GeoCLIP's quality.

## What was run

- Dataset `opera-commons-v1`, version `1ba7b76631f4` (manifest SHA-256 prefix). 59 geotagged Wikimedia Commons photos,
  all `user_contributed` style, from 15 places: 30 in the `seed` split (8 places), 29 in `heldout` (7 other places, so whole
  places are held out). Licences (CC0, public domain, CC BY 2.0/3.0/4.0) are recorded per image in `manifest.csv`;
  they were read from Commons metadata by a script and **not reviewed by a human** (`needs_human_review`).
- Model `geoclip-v1` (geoclip 1.2.3, local, CPU), no VLM clues (no `OPENAI_API_KEY`), seed 0, provisional thresholds.
- `cd backend && .venv/bin/python -m app.eval.cli run --dataset opera-commons-v1 --split heldout --model geoclip-v1 --seed 0`
  and the same through `POST /api/v1/evaluations`. Both gave `reproducible_hash` `0376af0d3dda...` for `heldout`; a second CLI run matched too.

## Results (top-1, all items, abstention ignored)

| split | n | median km | mean km | within 1 / 25 / 200 / 750 km | top-5 within 200 km | country acc. | top-5 country recall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| seed | 30 | 1.44 | 393.12 | 43% / 70% / 87% / 90% | 100% | 93% | 100% |
| heldout | 29 | 102.86 | 439.59 | 28% / 48% / 55% / 83% | 86% | 76% | 90% |

Latency p50 about 1.4 s per image on CPU (model load excluded). No cost (no VLM).

Reliability (observed share of top-1 within 200 km, per provisional confidence band): seed high 6/6, medium 13/14,
low 7/9; heldout high 9/14 (64%), medium 5/13 (38%), low 2/2. On heldout the bands are **not ordered by hit rate**, so the
band labels carry little information on this data.

## Caveats that matter

- Tiny sample, wide uncertainty: a single photo moves a percentage by 3 to 4 points. Per-country slices have 2 to 5 photos.
- **Training overlap cannot be ruled out.** GeoCLIP was trained on Flickr-style photos and Commons landmarks are widely
  scraped; a 1.4 km median on the seed split (Lisbon, Kyoto, Austin, Sydney, Zermatt...) suggests memorised landmarks.
  The heldout set is only "held out" from OPERA's calibration, not from the model's training data.
- Commons geotags sometimes mark the photographed object, not the camera. Some "errors" of a few km may be label noise.
- Selection: photos were picked by a script plus manual removal of indoor, people-focused and historical images. That
  choice favours recognisable outdoor scenes.

## Calibration attempt (not adopted)

`python -m app.eval.cli calibrate` fits thresholds on the seed split only. On this seed split even the lowest scores hit
within 200 km at over 80%, so the rule put all three cut-offs at 0.0048 (every photo "high"). Applied to heldout that
makes 55% of "high" answers correct, worse than the provisional thresholds shown above. The provisional values in
`backend/app/config.py` therefore **stay**, and every candidate still carries `uncalibrated: true`.
Real calibration needs a larger and harder seed set. See D44 in `docs/DECISIONS.md`.
