# afiliado

Gerador de **site estático fantasma** para afiliados: coleta ofertas (simuladas), escreve posts otimizados para SEO com Gemini e publica no GitHub Pages via Jekyll.

O site chama-se **Ofertas Infinitas**. O workflow do GitHub Actions roda todos os dias às **08:00 UTC**.

## Como funciona

1. `src/scraper.py` simula a busca de ofertas (nome, preço, link e imagem).
2. `src/seo_writer.py` gera Markdown persuasivo com a API Gemini e injeta a tag de afiliado.
3. `src/builder.py` orquestra o fluxo e grava em `_posts/YYYY-MM-DD-titulo-do-produto.md`.
4. O Jekyll (GitHub Pages) transforma os posts em um site estático rápido, sem JavaScript.

## Setup local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Preencha no `.env`:

- `GEMINI_API_KEY` — chave do [Google AI Studio](https://aistudio.google.com/apikey)
- `AFFILIATE_TAG` — sua tag Associates da Amazon (ex.: `minhaloja-20`)

Rode o gerador:

```bash
python src/builder.py
```

Os arquivos entram em `_posts/`. O modelo padrão é `gemini-3.6-flash` (o `gemini-2.0-flash` foi descontinuado). Sem a chave Gemini, o writer usa um template de fallback para o pipeline não parar. Posts do mesmo produto são atualizados no mesmo arquivo, sem criar URL duplicada.

## GitHub Actions e Pages

1. No repositório, crie os secrets:
   - `GEMINI_API_KEY`
   - `AFFILIATE_TAG`
2. Em **Settings → Pages**, escolha a branch `main` e a pasta `/ (root)`.
3. O workflow `.github/workflows/automacao.yml` dispara:
   - todo dia às 08:00 (cron);
   - ou manualmente em **Actions → Automação de ofertas → Run workflow**.

Termos de busca padrão ficam em `_config.yml` (`termos_busca`). Dá para sobrescrever com o secret `SEARCH_TERMS` (lista separada por vírgula).
