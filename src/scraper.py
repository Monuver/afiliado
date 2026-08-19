"""Simulador de busca de ofertas no estilo Amazon.

A classe `AmazonScraper` gera um catálogo HTML fictício, interpreta-o com
BeautifulSoup e devolve dicionários prontos para o writer de SEO. Qualquer
falha de rede é registrada e o fluxo segue com dados simulados — o pipeline
nunca depende de scraping real contra a Amazon (ToS).
"""

from __future__ import annotations

import hashlib
import logging
import random
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; OfertasInfinitas/1.0; +https://github.com/Monuver/afiliado)"
)
TIMEOUT_SEGUNDOS = 10
AMAZON_BASE = "https://www.amazon.com.br"

# Variações usadas para montar ofertas distintas a partir do mesmo termo.
_VARIANTES = (
    ("Kit Completo", 1.00, 4.6),
    ("Edição Premium", 1.35, 4.8),
    ("Compacto", 0.72, 4.4),
    ("com Garantia Estendida", 1.18, 4.7),
    ("Mais Vendido", 0.95, 4.5),
)


class AmazonScraper:
    """Busca (simulada) de ofertas a partir de um termo de pesquisa."""

    def __init__(self, timeout: int = TIMEOUT_SEGUNDOS) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "pt-BR,pt;q=0.9",
            }
        )

    def buscar_ofertas(self, termo: str, limite: int = 5) -> list[dict[str, str]]:
        """Recebe um termo de busca e devolve ofertas no formato esperado pelo builder.

        Cada item contém: ``nome``, ``preco``, ``link_original``, ``imagem``.
        """
        termo = (termo or "").strip()
        if not termo:
            logger.warning("Termo de busca vazio; nenhuma oferta será gerada.")
            return []

        limite = max(1, min(int(limite), len(_VARIANTES)))
        html = self._html_catalogo_simulado(termo, limite)
        ofertas = self._extrair_ofertas_do_html(html)

        if not ofertas:
            logger.warning(
                "Parser não extraiu ofertas para '%s'; usando fallback direto.", termo
            )
            ofertas = self._ofertas_diretas(termo, limite)

        logger.info("Encontradas %s oferta(s) para '%s'.", len(ofertas), termo)
        return ofertas

    def _html_catalogo_simulado(self, termo: str, limite: int) -> str:
        """Monta um HTML fictício de vitrine para ser parseado pelo BeautifulSoup."""
        cards: list[str] = []
        for produto in self._ofertas_diretas(termo, limite):
            cards.append(
                f"""
                <article class="product-card" data-asin="{produto["asin"]}">
                    <h2 class="product-title">{produto["nome"]}</h2>
                    <span class="product-price">{produto["preco"]}</span>
                    <a class="product-link" href="{produto["link_original"]}">ver oferta</a>
                    <img class="product-image" src="{produto["imagem"]}" alt="{produto["nome"]}">
                </article>
                """
            )
        return f'<div class="search-results">{"".join(cards)}</div>'

    def _extrair_ofertas_do_html(self, html: str) -> list[dict[str, str]]:
        """Interpreta o HTML da vitrine e devolve a lista de dicionários."""
        soup = BeautifulSoup(html, "html.parser")
        ofertas: list[dict[str, str]] = []

        for card in soup.select("article.product-card"):
            titulo = card.select_one(".product-title")
            preco = card.select_one(".product-price")
            link = card.select_one(".product-link")
            imagem = card.select_one(".product-image")

            nome = titulo.get_text(strip=True) if titulo else ""
            href = link.get("href", "") if link else ""
            src = imagem.get("src", "") if imagem else ""
            preco_txt = preco.get_text(strip=True) if preco else ""

            if not (nome and href):
                continue

            ofertas.append(
                {
                    "nome": nome,
                    "preco": preco_txt or "Consulte o preço",
                    "link_original": href,
                    "imagem": src,
                }
            )

        return ofertas

    def _ofertas_diretas(self, termo: str, limite: int) -> list[dict[str, Any]]:
        """Gera ofertas determinísticas (mesmo termo → mesmos ASINs fictícios)."""
        termo_titulo = " ".join(parte.capitalize() for parte in termo.split())
        semente = int(hashlib.sha256(termo.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(semente)
        preco_base = rng.uniform(79.9, 899.9)

        ofertas: list[dict[str, Any]] = []
        for indice, (rotulo, fator, _nota) in enumerate(_VARIANTES[:limite]):
            asin = self._asin_ficticio(termo, indice)
            preco = preco_base * fator
            ofertas.append(
                {
                    "asin": asin,
                    "nome": f"{termo_titulo} {rotulo}",
                    "preco": _formatar_preco_brl(preco),
                    "link_original": f"{AMAZON_BASE}/dp/{asin}",
                    "imagem": (
                        "https://picsum.photos/seed/"
                        f"{quote_plus(asin)}/640/640"
                    ),
                }
            )
        return ofertas

    @staticmethod
    def _asin_ficticio(termo: str, indice: int) -> str:
        digest = hashlib.sha256(f"{termo}:{indice}".encode("utf-8")).hexdigest()
        # ASINs da Amazon têm 10 caracteres alfanuméricos.
        return f"B0{digest[:8].upper()}"


def _formatar_preco_brl(valor: float) -> str:
    inteiro, centavos = f"{valor:.2f}".split(".")
    grupos: list[str] = []
    while inteiro:
        grupos.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    inteiro_fmt = ".".join(reversed(grupos))
    return f"R$ {inteiro_fmt},{centavos}"
