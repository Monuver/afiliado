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

from afiliado_links import eh_link_curto_afiliado

logger = logging.getLogger(__name__)

# A API devolve 404 para gemini-2.0-flash; o endpoint recomenda gemini-3.6-flash.
MODELO_PADRAO = "gemini-3.6-flash"
MODELOS_RESERVA = (
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
)

_modelo_ok: str | None = None


def gerar_post_markdown(produto: dict[str, Any]) -> str:
    """Recebe os dados de um produto e devolve um post completo em Markdown.

    O conteúdo inclui título H1 chamativo, descrição persuasiva e CTA com a
    tag de afiliado definida em ``AFFILIATE_TAG``.
    """
    tag = os.getenv("AFFILIATE_TAG", "").strip()
    url = produto.get("link_original", "")
    if produto.get("tipo") == "link_afiliado" or eh_link_curto_afiliado(str(url)):
        link_afiliado = str(url)
    else:
        link_afiliado = aplicar_tag_afiliado(url, tag)
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


def _candidatos_de_modelo() -> list[str]:
    escolhido = os.getenv("GEMINI_MODEL", "").strip()
    cadeia: list[str] = []
    if escolhido:
        cadeia.append(escolhido)
    for nome in MODELOS_RESERVA:
        if nome not in cadeia:
            cadeia.append(nome)
    return cadeia


def _gerar_com_gemini(produto: dict[str, Any]) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY não definida; pulando a geração via IA.")
        return None

    global _modelo_ok
    prompt = _montar_prompt(produto)
    genai.configure(api_key=api_key)

    modelos = _candidatos_de_modelo()
    if _modelo_ok:
        modelos = [_modelo_ok] + [nome for nome in modelos if nome != _modelo_ok]
    ultimo_erro: Exception | None = None

    for modelo_nome in modelos:
        if not modelo_nome:
            continue
        try:
            modelo = genai.GenerativeModel(modelo_nome)
            resposta = modelo.generate_content(prompt)
            texto = (getattr(resposta, "text", None) or "").strip()
            if not texto:
                logger.warning("Gemini (%s) devolveu resposta vazia.", modelo_nome)
                continue
            if _modelo_ok != modelo_nome:
                logger.info("Gemini ativo com o modelo %s.", modelo_nome)
                _modelo_ok = modelo_nome
            return texto
        except Exception as exc:  # SDK Gemini levanta tipos variados (rede, quota, auth).
            ultimo_erro = exc
            logger.warning(
                "Modelo %s indisponível (%s): %s",
                modelo_nome,
                type(exc).__name__,
                exc,
            )
            if _modelo_ok == modelo_nome:
                _modelo_ok = None
            continue

    if ultimo_erro is not None:
        logger.error(
            "Falha ao gerar conteúdo com Gemini (%s): %s",
            type(ultimo_erro).__name__,
            ultimo_erro,
        )
    return None


def _montar_prompt(produto: dict[str, Any]) -> str:
    nome = produto.get("nome", "Produto em oferta")
    preco = produto.get("preco", "preço sob consulta")
    link = produto.get("link_afiliado") or produto.get("link_original", "#")
    imagem = produto.get("imagem", "")
    caracteristicas = str(produto.get("caracteristicas") or "").strip()
    termo = str(produto.get("termo") or "").strip()
    if produto.get("tipo") == "busca":
        return f"""Você é um copywriter sênior de SEO para um site brasileiro de ofertas de afiliados.

Escreva UM guia de compra em Markdown (sem front matter YAML) sobre a categoria abaixo.

Categoria de busca: {termo or nome}
Página de ofertas ao vivo na Amazon (use exatamente este URL no CTA): {link}

Regras obrigatórias:
- Comece com um único H1 chamativo com a palavra-chave da categoria.
- Primeiro parágrafo: resumo persuasivo (máx. 160 caracteres de intenção de meta description).
- NÃO invente modelo, marca, ASIN, preço fechado nem foto de produto específico.
- NÃO invente que um item específico está em promoção; o preço real está na Amazon.
- Use H2/H3 para: o que avaliar antes de comprar, para quem é indicado, mini FAQ (3 perguntas).
- Linguagem em português do Brasil, tom direto, sem clichês de "melhor do mundo".
- Feche com um H2 de call-to-action e UM único link Markdown, exatamente assim:
  [Confira as ofertas atualizadas na Amazon]({link})
- Não inclua a palavra "afiliado" no texto visível.
- Não use blocos de código. Não use front matter. Não explique o que você fez.
"""

    bloco_features = (
        f"Características oficiais (use só estas; não invente spec): {caracteristicas}"
        if caracteristicas
        else "Características oficiais: não informadas. Não invente especificações técnicas."
    )
    regra_imagem = (
        f"- Inclua a imagem com a sintaxe Markdown: ![{nome}]({imagem})"
        if imagem
        else "- Não inclua imagem (não há URL oficial)."
    )

    return f"""Você é um copywriter sênior de SEO para um site brasileiro de ofertas de afiliados.

Escreva UM post completo em Markdown (sem front matter YAML) sobre o produto abaixo.

Produto: {nome}
Preço anunciado: {preco}
Link de afiliado (use exatamente este URL no CTA): {link}
Imagem: {imagem}
{bloco_features}

Regras obrigatórias:
- Comece com um único H1 chamativo, incluindo a palavra-chave principal de forma natural.
- Primeiro parágrafo: resumo persuasivo (máx. 160 caracteres de intenção de meta description).
{regra_imagem}
- Use H2/H3 para benefícios, para quem é indicado e um mini FAQ (3 perguntas) visando featured snippet.
- Linguagem em português do Brasil, tom direto, sem clichês de "melhor do mundo".
- Não invente especificações técnicas. Só cite o que estiver no nome ou nas características oficiais.
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
    termo = str(produto.get("termo") or nome).strip()

    if produto.get("tipo") == "busca":
        return f"""# {termo}: o que vale a pena olhar agora

Se você está pesquisando **{termo}**, o caminho mais honesto é comparar as ofertas ao vivo na Amazon — preço, estoque e frete mudam o tempo todo.

## O que avaliar antes de comprar

- Preço do dia, não um valor “travado” em blog.
- Avaliação de quem já comprou e política de troca do vendedor.
- Frete e prazo na sua região, visíveis só na página da Amazon.

## Para quem é indicado

Quem quer resolver a compra hoje, com nota fiscal e rastreio, sem abrir dezenas de lojas.

## Mini FAQ

### Qual o preço certo de {termo}?
O preço válido é o da Amazon no instante do clique. Esta página só aponta para a busca atualizada.

### Tem garantia?
A garantia é a do vendedor na página do produto, na Amazon.

### Como aproveitar?
Abra a busca, compare duas ou três opções e feche se o conjunto preço + prazo fizer sentido.

## Veja as ofertas de agora

[Confira as ofertas atualizadas na Amazon]({link})
"""

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
