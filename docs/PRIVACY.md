# OPERA privacy and scope

OPERA estimates **where a photograph was taken** from the scenery in it (terrain, vegetation, roads, architecture,
signage). That is the whole scope.

## Prohibited uses (not built, not accepted as contributions)

- Face recognition, face matching or any search for a person.
- Matching people across images, or resolving who someone is.
- Reconstructing a person's movements or location history, or tracking anyone over time.
- Covert collection: analysing images the user has no right to analyse. The upload requires an explicit rights attestation.
- Scraping Google Maps/Earth or bulk-downloading datasets whose terms forbid it.

There are no face detection or identification code paths in this repository. The VLM prompt tells the model to ignore
people entirely and to abstain on images with no usable scenery (`backend/app/adapters/vlm_clues.py`).

## What happens to an uploaded image

1. Upload requires the API key and `rights_attested=true`. Type is checked by magic bytes; size, pixel count and request
   rate are limited.
2. The image is re-encoded server-side: EXIF, XMP, IPTC and GPS never reach storage, the model or any third party
   (covered by tests, including a check that the output bytes contain no GPS data).
3. The sanitized image is stored under `backend/uploads/` (git-ignored) with its analysis, private to the API key plus
   analysis id. It is deleted by `DELETE /api/v1/analyses/{id}` or by the sweeper after `OPERA_UPLOAD_TTL_HOURS`
   (default 24). Deleting removes the file and all rows.
4. With "use VLM clues" on, the downscaled sanitized image goes to the OpenAI API (only when `OPENAI_API_KEY` is set).
   OpenAI's retention terms apply to that call; no automatic face or plate blurring is implemented (the optional item
   in the spec was not built). Turn the option off to keep the image local.
5. Place names: only coordinates rounded to 3 decimals go to OSM Nominatim (never the image). Set
   `OPERA_CONTEXT_ENABLED=false` to disable.
6. The audit log records request id, endpoint, model, HTTP status and a salted hash of the client address; never image content,
   filenames or raw IP addresses.

## Output honesty

- Scores are raw model outputs, never probabilities, never averaged across models, always labelled `uncalibrated`.
- Output from the mock adapter or mock clues is labelled `mock` in the API and `MOCK` in the UI.
- Licences are `needs_human_review` until a person has read the actual licence text.

## Secrets and data in git

Keys live only in `.env` (git-ignored; `.env.example` has names only). Uploads, databases, model weights and downloaded
benchmark images are git-ignored.
