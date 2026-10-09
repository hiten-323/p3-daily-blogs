# Image generation provider setup

The existing generation module now supports Pixazo and the optional self-hosted
Cloudflare Worker from [saurav-z/free-image-generation-api](https://github.com/saurav-z/free-image-generation-api).

## Provider order

1. Pixazo, when `PIXAZO_API_KEY` is present.
2. The free-image-generation-api Worker, when both its URL and API key are configured.
3. Existing Hugging Face, Pollinations, and optional fal.ai providers.
4. Existing branded real-jar composition fallback.

Provider failures fall through; they do not cause a social post to be published.
The Instagram publisher's rendered-asset QA and real-jar provenance gates remain
in force. A text-to-image API cannot inspect local reference file paths, so its
output is not treated as verified product packaging. Keep final product posts on
the real-jar composition path unless an image-to-image workflow has been
explicitly implemented and verified.

## Pixazo

Configure the repository secret `PIXAZO_API_KEY` (legacy alias `PIXAZO_KEY`
is also supported). By default, the generator submits to
`https://gateway.pixazo.ai/flux/text-to-image`. To use a different Pixazo model
endpoint, define repository variable `PIXAZO_IMAGE_ENDPOINT`. The client sends
the key in `Ocp-Apim-Subscription-Key`, accepts immediate image URLs, and polls
the Pixazo request-status endpoint when the response contains a `request_id`.

The default model endpoint and request fields should be adjusted if your Pixazo
account is enabled for a different model or requires different generation
parameters.

## Self-hosted free API

The linked GitHub project is **source code to deploy**, not a hosted public URL.
Deploy its `worker.js` into your own Cloudflare account, enable Workers AI,
bind the Worker service as `AI`, and configure the Worker environment variable
`API_KEY`. The Worker URL must end at its root `/` endpoint because this
implementation accepts `POST /`.

Then configure these repository settings:

- Repository variable `FREE_IMAGE_API_URL`: your deployed Worker URL, e.g.
  `https://your-worker.your-subdomain.workers.dev`.
- Repository secret `FREE_IMAGE_API_KEY`: the exact same value as the Worker's
  `API_KEY` environment variable.

Compatibility aliases supported for the secret are `CLOUDFLARE_IMAGE_API_KEY`
and `API_KEY`; prefer the scoped `FREE_IMAGE_API_KEY` name. The Worker URL can
also be stored as secret `FREE_IMAGE_API_URL` if you prefer.

The client sends `Authorization: Bearer <key>` and `{"prompt":"..."}`, expects
raw image bytes, and rejects JSON error responses. Width/height and seed are not
forwarded because the upstream Worker currently accepts only `prompt`.

## Safe validation

Tests mock provider responses and do not spend Pixazo credits or call Cloudflare.
To verify live credentials, run the existing daily workflow with `dry_run`
enabled only after provider connectivity has been added to a dedicated probe.
The normal daily pipeline is not invoked as a live-generation test here, and no
social content is published by these tests.
