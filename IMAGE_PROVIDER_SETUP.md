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
