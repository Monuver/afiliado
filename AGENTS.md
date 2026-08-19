# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single product ("Ofertas Infinitas") with two parts:

1. A Python content-generation pipeline in `src/` (entry point `python src/builder.py`) that
   searches **real** Amazon Brazil products and writes affiliate posts into `_posts/`.
2. A Jekyll static site (root `_config.yml`, `_layouts/`, `index.md`, `_posts/`) that GitHub
   Pages renders in production.

Standard setup/run commands live in `README.md`. Notes below are the non-obvious bits.

### Python generator
- Activate the venv before running: `source .venv/bin/activate`, then `python src/builder.py`.
- Real catalog requires Amazon Creators API credentials in the environment:
  `AMAZON_CREDENTIAL_ID`, `AMAZON_CREDENTIAL_SECRET`, optional `AMAZON_CREDENTIAL_VERSION`
  (default `3.1` for Brazil/NA), plus `AFFILIATE_TAG`. Without the credential pair the
  builder exits with `CatalogoNaoConfigurado` instead of inventing products.
- Do **not** scrape Amazon. The official replacement for PA-API 5 is Creators API
  (`https://creatorsapi.amazon/catalog/v1/searchItems`).
- `ALLOW_SIMULATED=1` is the only way to get the old fake catalog; never use it for
  published posts.
- Gemini (`GEMINI_API_KEY`) writes the SEO copy. If the key is missing/invalid, the writer
  falls back to a Markdown template. `.env.example` ships a placeholder
  `GEMINI_API_KEY=sua_chave_aqui` — that produces a noisy `API_KEY_INVALID` before fallback.
- `builder.py` reuses the existing file for a given product slug (`*-<slug>.md`) instead of
  creating a new dated file.

### Jekyll site (local preview)
- There is intentionally **no Gemfile**; production rendering is handled by GitHub Pages.
- `_config.yml` sets `baseurl: "/afiliado"`, so the served site is at
  `http://localhost:4000/afiliado/` (not `http://localhost:4000/`).
- Serve with `jekyll serve --host 0.0.0.0 --port 4000`.

### Tests / lint
- There is no automated test suite. Smoke check: `python -m compileall src` and import the
  modules. Mapping from Creators API JSON can be checked via `scraper.extrair_oferta`.
