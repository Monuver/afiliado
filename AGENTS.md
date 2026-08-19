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
- Real ads work with just `AFFILIATE_TAG`: the generator builds live Amazon search
  URLs (`amazon.com.br/s?k=...`) instead of fake ASINs. Creators API credentials
  (`AMAZON_CREDENTIAL_ID` / `AMAZON_CREDENTIAL_SECRET`) are optional — Amazon often
  blocks new Associates (red X on “conta aprovada”, and catalog access typically
  needs ~10 qualifying sales in 30 days). If those keys exist, `searchItems` is
  tried first; on failure/ineligibility it falls back to search links.
- Do **not** scrape Amazon.
- `ALLOW_SIMULATED=1` is the only way to get the old fake catalog; never use it for
  published posts.
- Missing `AFFILIATE_TAG` raises `CatalogoNaoConfigurado`. Missing Creators API keys
  does **not** abort the run.
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
