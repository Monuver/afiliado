# afiliado

Gerador de **site estático** para afiliados: busca ofertas **reais** na Amazon Brasil (Creators API), escreve posts otimizados para SEO com Gemini e publica no GitHub Pages via Jekyll.

O site chama-se **Ofertas Infinitas**. O workflow do GitHub Actions roda todos os dias às **08:00 UTC**.

## Como funciona

1. `src/scraper.py` consulta o catálogo oficial da Amazon (Creators API) e devolve nome, preço, imagem e link.
2. `src/seo_writer.py` gera Markdown persuasivo com a API Gemini, usando só as características oficiais do produto, e injeta a tag de afiliado.
3. `src/builder.py` orquestra o fluxo e grava em `_posts/YYYY-MM-DD-titulo-do-produto.md`.
4. O Jekyll (GitHub Pages) transforma os posts em um site estático rápido, sem JavaScript.

Scraping da Amazon **não é usado** (viola os termos). Sem as credenciais da Creators API o gerador para, em vez de inventar produto.

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
- `AMAZON_CREDENTIAL_ID` / `AMAZON_CREDENTIAL_SECRET` — em Associates Central → **Tools → Creators API** → Create Application → Create Credential
- `AMAZON_CREDENTIAL_VERSION` — a versão que a Amazon mostrar na credencial (Brasil/NA costuma ser `3.1`)

Rode o gerador:

```bash
python src/builder.py
```

Os arquivos entram em `_posts/`. O modelo padrão é `gemini-3.6-flash`. Sem a chave Gemini, o writer usa um template de fallback para o pipeline não parar. Posts do mesmo produto são atualizados no mesmo arquivo, sem criar URL duplicada.

## GitHub Actions e Pages

1. No repositório, crie os secrets:
   - `GEMINI_API_KEY`
   - `AFFILIATE_TAG`
   - `AMAZON_CREDENTIAL_ID`
   - `AMAZON_CREDENTIAL_SECRET`
   - `AMAZON_CREDENTIAL_VERSION` (opcional; default `3.1`)
2. Em **Settings → Pages**, escolha a branch `main` e a pasta `/ (root)`.
3. O workflow `.github/workflows/automacao.yml` dispara:
   - todo dia às 08:00 (cron);
   - ou manualmente em **Actions → Automação de ofertas → Run workflow**.

Termos de busca padrão ficam em `_config.yml` (`termos_busca`). Dá para sobrescrever com o secret `SEARCH_TERMS` (lista separada por vírgula).
