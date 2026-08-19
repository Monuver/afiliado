# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single product ("Ofertas Infinitas") with two parts:

1. A Python content-generation pipeline in `src/` (entry point `python src/builder.py`) that
   builds affiliate offer posts into `_posts/`.
2. A Jekyll static site (root `_config.yml`, `_layouts/`, `index.md`, `_posts/`) that GitHub
   Pages renders in production.

Standard setup/run commands live in `README.md`; the update script already installs the Python
dependencies into `.venv`. Notes below are the non-obvious bits.

### Python generator
- Activate the pre-created venv before running: `source .venv/bin/activate`, then `python src/builder.py`.
- The pipeline runs fully offline. `src/scraper.py` only *simulates* Amazon results (it never hits
  the network), and `src/seo_writer.py` falls back to a Markdown template when Gemini is unavailable,
  so the run never fails hard.
- Gotcha: `.env.example` ships a placeholder `GEMINI_API_KEY=sua_chave_aqui`. Copying it to `.env`
  makes the writer attempt Gemini and log a noisy `API_KEY_INVALID` warning before falling back. To
  silence it, leave `GEMINI_API_KEY` empty (writer then skips AI and goes straight to the template),
  or set a real key from Google AI Studio.
- Useful overrides for a quick, isolated test run (avoids touching the tracked default posts):
  `SEARCH_TERMS="some product" MAX_OFERTAS=1 python src/builder.py`.
- `builder.py` reuses the existing file for a given product slug (`*-<slug>.md`) instead of creating
  a new dated file, so re-running updates in place rather than duplicating URLs.

### Jekyll site (local preview)
- There is intentionally **no Gemfile**; production rendering is handled by GitHub Pages. For local
  preview, Ruby + Jekyll + the plugins (`jekyll-seo-tag`, `jekyll-sitemap`, `jekyll-feed`) are
  installed at the system level (baked into the VM), so `jekyll build` / `jekyll serve` work directly.
- Gotcha: `_config.yml` sets `baseurl: "/afiliado"`, so the served site is at
  `http://localhost:4000/afiliado/` (not `http://localhost:4000/`). Post permalinks are
  `/afiliado/ofertas/<title-slug>/`.
- Serve with `jekyll serve --host 0.0.0.0 --port 4000`.

### Tests / lint
- There is no automated test suite and no configured linter in this repo. For a smoke check use
  `python -m compileall src` and import the modules.
