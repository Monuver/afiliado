# afiliado

Gerador de **site estático** para afiliados: publica anúncios **reais** da Amazon Brasil (busca ao vivo com a sua tag; e catálogo via Creators API quando a Amazon liberar), escreve posts com Gemini e sobe no GitHub Pages via Jekyll.

O site chama-se **Ofertas Infinitas**. O workflow do GitHub Actions roda todos os dias às **08:00 UTC**.

## Como funciona

1. `src/builder.py` lê `links_afiliado` em `_config.yml` (ou o secret/env `AFFILIATE_LINKS`).
2. `src/afiliado_links.py` abre cada `amzn.to` / `/dp/` que você passou, pega nome, preço e foto, e **mantém o seu link curto no CTA**.
3. Se a lista de links estiver vazia, cai no modo busca (`amazon.com.br/s?k=...`) ou na Creators API, se a Amazon tiver liberado.
4. `src/seo_writer.py` gera o Markdown com Gemini.
5. O Jekyll (GitHub Pages) publica o site.

Para adicionar produto novo, cole o `amzn.to` em `_config.yml` na lista `links_afiliado` e rode `python src/builder.py`.

Scraping da Amazon **não é usado** (viola os termos). A Creators API exige conta Associates aprovada e, para catálogo de produto, em geral **10 vendas qualificadas nos últimos 30 dias**. Conta nova usa o modo busca até a Amazon liberar a API.

## Setup local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Preencha no `.env`:

- `GEMINI_API_KEY` — chave do [Google AI Studio](https://aistudio.google.com/apikey)
- `AFFILIATE_TAG` — sua tag Associates da Amazon (ex.: `minhaloja-20`) — **obrigatória**
- `AMAZON_CREDENTIAL_ID` / `AMAZON_CREDENTIAL_SECRET` — opcional, só quando a Amazon liberar Creators API na sua conta
- `AMAZON_CREDENTIAL_VERSION` — a versão da credencial (Brasil/NA costuma ser `3.1`)

Rode o gerador:

```bash
python src/builder.py
```

Os arquivos entram em `_posts/`. O modelo padrão é `gemini-3.6-flash`. Sem a chave Gemini, o writer usa um template de fallback para o pipeline não parar. Posts do mesmo produto são atualizados no mesmo arquivo, sem criar URL duplicada.

## GitHub Actions e Pages

1. No repositório, crie os secrets:
   - `GEMINI_API_KEY`
   - `AFFILIATE_TAG`
   - `AMAZON_CREDENTIAL_ID` / `AMAZON_CREDENTIAL_SECRET` (opcional, quando a API estiver liberada)
   - `AMAZON_CREDENTIAL_VERSION` (opcional; default `3.1`)
2. Em **Settings → Pages**, escolha a branch `main` e a pasta `/ (root)`.
3. O workflow `.github/workflows/automacao.yml` dispara:
   - todo dia às 08:00 (cron);
   - ou manualmente em **Actions → Automação de ofertas → Run workflow**.

Termos de busca padrão ficam em `_config.yml` (`termos_busca`). Dá para sobrescrever com o secret `SEARCH_TERMS` (lista separada por vírgula).
