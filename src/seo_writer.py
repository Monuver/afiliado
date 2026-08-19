"""Geração de posts Markdown otimizados para SEO via Google Gemini."""

from __future__ import annotations

import logging
import os
import re
import warnings
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

warnings.filterwarnings("ignore", category=FutureWarning)
import google.generativeai as genai

logger = logging.getLogger(__name__)

MODELO_PADRAO = "gemini-2.0-flash"


def gerar_post_markdown(produto: dict[str, Any]) -> str:
    """Recebe os dados de um produto e devolve um post completo em Markdown.

    O conteúdo inclui título H1 chamativo, descrição persuasiva e CTA com a
    tag de afiliado definida em ``AFFILIATE_TAG``.
    """
    tag = os.getenv("AFFILIATE_TAG", "").strip()
    link_afiliado = aplicar_tag_afiliado(produto.get("link_original", ""), tag)
    produto_enriquecido = {**produto, "link_afiliado": link_afiliado, "tag": tag}

    corpo = _gerar_com_gemini(produto_enriquecido)
    if not corpo:
        logger.warning(
            "Gemini indisponível para '%s'; usando template de fallback.",
            produto.get("nome"),
        )
        corpo = _gerar_fallback_markdown(produto_enriquecido)

    return _garantir_cta(corpo, produto_enriquecido)


def aplicar_tag_afiliado(url: str, tag: str) -> str:
    """Anexa (ou substitui) o parâmetro ``tag`` da Amazon no link original."""
    if not url:
        return ""
    if not tag:
        return url

    partes = urlsplit(url)
    query = dict(parse_qsl(partes.query, keep_blank_values=True))
    query["tag"] = tag
    return urlunsplit(
        (partes.scheme, partes.netloc, partes.path, urlencode(query), partes.fragment)
    )


def _gerar_com_gemini(produto: dict[str, Any]) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY não definida; pulando a geração via IA.")
        return None

    modelo_nome = os.getenv("GEMINI_MODEL", MODELO_PADRAO).strip() or MODELO_PADRAO
    prompt = _montar_prompt(produto)

    try:
        genai.configure(api_key=api_key)
        modelo = genai.GenerativeModel(modelo_nome)
        resposta = modelo.generate_content(prompt)
        texto = (getattr(resposta, "text", None) or "").strip()
        return texto or None
    except Exception as exc:  # SDK Gemini levanta tipos variados (rede, quota, auth).
        logger.error("Falha ao gerar conteúdo com Gemini (%s): %s", type(exc).__name__, exc)
        return None


def _montar_prompt(produto: dict[str, Any]) -> str:
    nome = produto.get("nome", "Produto em oferta")
    preco = produto.get("preco", "preço sob consulta")
    link = produto.get("link_afiliado") or produto.get("link_original", "#")
    imagem = produto.get("imagem", "")

    return f"""Você é um copywriter sênior de SEO para um site brasileiro de ofertas de afiliados.

Escreva UM post completo em Markdown (sem front matter YAML) sobre o produto abaixo.

Produto: {nome}
Preço anunciado: {preco}
Link de afiliado (use exatamente este URL no CTA): {link}
Imagem: {imagem}

Regras obrigatórias:
- Comece com um único H1 chamativo, incluindo a palavra-chave principal de forma natural.
- Primeiro parágrafo: resumo persuasivo (máx. 160 caracteres de intenção de meta description).
- Inclua a imagem com a sintaxe Markdown: ![{nome}]({imagem})
- Use H2/H3 para benefícios, para quem é indicado e um mini FAQ (3 perguntas) visando featured snippet.
- Linguagem em português do Brasil, tom direto, sem clichês de "melhor do mundo".
- Não invente especificações técnicas que não estejam no nome do produto.
- Feche com um H2 de call-to-action e UM único link Markdown, exatamente assim:
  [Confira o preço atualizado na Amazon]({link})
- Não inclua a palavra "afiliado" no texto visível; o CTA deve ser claro e honesto ("ver preço", "comprar").
- Não use blocos de código. Não use front matter. Não explique o que você fez.
"""


def _gerar_fallback_markdown(produto: dict[str, Any]) -> str:
    nome = produto.get("nome", "Oferta selecionada")
    preco = produto.get("preco", "Consulte o preço")
    link = produto.get("link_afiliado") or produto.get("link_original", "#")
    imagem = produto.get("imagem", "")

    bloco_imagem = f"![{nome}]({imagem})\n\n" if imagem else ""

    return f"""# {nome}: vale a pena agora?

{nome} está com preço anunciado de **{preco}**. Se você já pesquisava essa categoria, esta página reúne o essencial para decidir rápido — sem enrolação.

{bloco_imagem}## Por que esta oferta se destaca

- Preço transparente na ficha: **{preco}**.
- Link direto para a página oficial da Amazon, onde estoque e frete são atualizados em tempo real.
- Indicação pensada para quem quer resolver a compra hoje, sem abrir dezenas de abas.

## Para quem é indicado

Ideal para quem busca **{nome}** com boa relação custo-benefício e prefere comprar em um marketplace conhecido, com nota fiscal e rastreio.

## Mini FAQ

### O preço de {preco} está garantido?
O valor anunciado aqui é o que coletamos no momento da publicação. O preço final é sempre o da Amazon no instante do clique.

### Tem garantia?
A garantia é a oferecida pelo vendedor na página do produto. Confira as condições antes de fechar.

### Como aproveitar a oferta?
Toque no botão abaixo, valide o preço atualizado e conclua a compra se fizer sentido para você.

## Aproveite enquanto o preço estiver assim

[Confira o preço atualizado na Amazon]({link})
"""


def _garantir_cta(markdown: str, produto: dict[str, Any]) -> str:
    """Garante que o post termine com um CTA contendo o link de afiliado."""
    link = produto.get("link_afiliado") or produto.get("link_original", "")
    if not link:
        return markdown.strip()

    if link in markdown:
        return markdown.strip()

    cta = (
        "\n\n## Aproveite enquanto o preço estiver assim\n\n"
        f"[Confira o preço atualizado na Amazon]({link})\n"
    )
    # Evita duplicar um H2 de CTA se o modelo gerou outro texto.
    if re.search(r"\[.*?\]\([^)]+\)", markdown):
        return markdown.strip() + cta
    return markdown.strip() + cta
