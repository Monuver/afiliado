"""Catálogo de ofertas da Amazon Brasil.

Caminhos, em ordem:

1. Creators API, se ``AMAZON_CREDENTIAL_ID`` e ``AMAZON_CREDENTIAL_SECRET``
   existirem — produtos específicos (ASIN, preço, foto).
2. Links de busca reais ``amazon.com.br/s?k=...`` com a ``AFFILIATE_TAG`` —
   funciona sem a API (contas novas a Amazon ainda não libera a Creators API).
3. Catálogo fictício só com ``ALLOW_SIMULATED=1`` (desenvolvimento).

Scraping da Amazon continua fora de questão (ToS).
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import time
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; OfertasInfinitas/1.0; +https://github.com/Monuver/afiliado)"
)
TIMEOUT_SEGUNDOS = 20
AMAZON_BASE = "https://www.amazon.com.br"
MARKETPLACE = "www.amazon.com.br"
CREATORS_SEARCH_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"
INTERVALO_MINIMO_S = 1.1

TOKEN_ENDPOINTS = {
    "3.1": "https://api.amazon.com/auth/o2/token",
    "3.2": "https://api.amazon.co.uk/auth/o2/token",
    "3.3": "https://api.amazon.co.jp/auth/o2/token",
    "2.1": "https://creatorsapi.auth.us-east-1.amazoncognito.com/oauth2/token",
    "2.2": "https://creatorsapi.auth.eu-south-2.amazoncognito.com/oauth2/token",
    "2.3": "https://creatorsapi.auth.us-west-2.amazoncognito.com/oauth2/token",
}

SEARCH_RESOURCES = (
    "itemInfo.title",
    "itemInfo.features",
    "images.primary.hiRes",
    "images.primary.large",
    "images.primary.medium",
    "images.primary.small",
    "offersV2.listings.price",
    "offersV2.listings.availability",
)

_VARIANTES = (
    ("Kit Completo", 1.00, 4.6),
    ("Edição Premium", 1.35, 4.8),
    ("Compacto", 0.72, 4.4),
    ("com Garantia Estendida", 1.18, 4.7),
    ("Mais Vendido", 0.95, 4.5),
)


class CatalogoNaoConfigurado(RuntimeError):
    """Falta a tag de afiliado, necessária para montar links reais da Amazon."""


class AmazonScraper:
    """Busca ofertas reais na Amazon Brasil (Creators API)."""

    def __init__(self, timeout: int = TIMEOUT_SEGUNDOS) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "pt-BR,pt;q=0.9",
            }
        )
        self._token: str | None = None
        self._token_expira_em: float = 0.0
        self._ultima_busca: float = 0.0

    def buscar_ofertas(self, termo: str, limite: int = 5) -> list[dict[str, str]]:
        """Recebe um termo de busca e devolve ofertas no formato do builder.

        Cada item contém: ``nome``, ``preco``, ``link_original``, ``imagem``
        e, quando a API envia, ``caracteristicas`` e ``asin``.
        """
        termo = (termo or "").strip()
        if not termo:
            logger.warning("Termo de busca vazio; nenhuma oferta será gerada.")
            return []

        limite = max(1, min(int(limite), 10))

        if _simulacao_liberada():
            logger.warning(
                "ALLOW_SIMULATED=1: gerando catálogo fictício para '%s'.", termo
            )
            return self._buscar_simuladas(termo, limite)

        partner_tag = os.getenv("AFFILIATE_TAG", "").strip()
        if not partner_tag:
            raise CatalogoNaoConfigurado(
                "AFFILIATE_TAG vazia. Sem a tag Associates não dá para montar "
                "links reais da Amazon."
            )

        if _creators_configurada():
            try:
                ofertas = self._buscar_creators_api(termo, limite, partner_tag)
                if ofertas:
                    logger.info(
                        "Encontradas %s oferta(s) via Creators API para '%s'.",
                        len(ofertas),
                        termo,
                    )
                    return ofertas
                logger.warning(
                    "Creators API não devolveu itens para '%s'; usando busca Amazon.",
                    termo,
                )
            except Exception as exc:
                logger.warning(
                    "Creators API indisponível para '%s' (%s: %s); usando busca Amazon.",
                    termo,
                    type(exc).__name__,
                    exc,
                )

        ofertas = montar_ofertas_busca(termo, limite=1)
        logger.info(
            "Montada(s) %s busca(s) real(is) na Amazon para '%s'.",
            len(ofertas),
            termo,
        )
        return ofertas

    def _buscar_creators_api(
        self, termo: str, limite: int, partner_tag: str
    ) -> list[dict[str, str]]:
        credential_id = os.getenv("AMAZON_CREDENTIAL_ID", "").strip()
        credential_secret = os.getenv("AMAZON_CREDENTIAL_SECRET", "").strip()
        version = os.getenv("AMAZON_CREDENTIAL_VERSION", "3.1").strip() or "3.1"

        token = self._obter_token(credential_id, credential_secret, version)
        self._respeitar_rate_limit()

        corpo = {
            "keywords": termo,
            "itemCount": limite,
            "partnerTag": partner_tag,
            "partnerType": "Associates",
            "marketplace": MARKETPLACE,
            "resources": list(SEARCH_RESOURCES),
        }
        headers = {
            "Authorization": _cabecalho_bearer(token, version),
            "Content-Type": "application/json",
            "x-marketplace": MARKETPLACE,
        }
        resposta = self.session.post(
            CREATORS_SEARCH_URL,
            json=corpo,
            headers=headers,
            timeout=self.timeout,
        )
        if resposta.status_code >= 400:
            logger.error(
                "Creators API recusou a busca por '%s' (%s): %s",
                termo,
                resposta.status_code,
                resposta.text[:500],
            )
            resposta.raise_for_status()

        dados = resposta.json() if resposta.content else {}
        itens = _itens_da_resposta(dados)
        ofertas = []
        for item in itens:
            oferta = extrair_oferta(item)
            if oferta:
                ofertas.append(oferta)
        return ofertas[:limite]

    def _obter_token(self, credential_id: str, credential_secret: str, version: str) -> str:
        agora = time.time()
        if self._token and agora < self._token_expira_em:
            return self._token

        endpoint = TOKEN_ENDPOINTS.get(version)
        if not endpoint:
            conhecidas = ", ".join(sorted(TOKEN_ENDPOINTS))
            raise CatalogoNaoConfigurado(
                f"AMAZON_CREDENTIAL_VERSION={version!r} desconhecida. Use uma de: {conhecidas}."
            )

        if version.startswith("2."):
            resposta = self.session.post(
                endpoint,
                data={
                    "grant_type": "client_credentials",
                    "scope": "creatorsapi/default",
                },
                auth=(credential_id, credential_secret),
                timeout=self.timeout,
            )
        else:
            resposta = self.session.post(
                endpoint,
                json={
                    "grant_type": "client_credentials",
                    "client_id": credential_id,
                    "client_secret": credential_secret,
                    "scope": "creatorsapi::default",
                },
                timeout=self.timeout,
            )

        if resposta.status_code >= 400:
            logger.error(
                "Falha ao obter token da Creators API (%s): %s",
                resposta.status_code,
                resposta.text[:400],
            )
            resposta.raise_for_status()

        payload = resposta.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("Creators API devolveu token vazio.")
        expires_in = int(payload.get("expires_in") or 3600)
        self._token = token
        self._token_expira_em = time.time() + max(60, expires_in - 60)
        logger.info("Token da Creators API renovado (versão %s).", version)
        return token

    def _respeitar_rate_limit(self) -> None:
        elapsed = time.time() - self._ultima_busca
        if elapsed < INTERVALO_MINIMO_S:
            time.sleep(INTERVALO_MINIMO_S - elapsed)
        self._ultima_busca = time.time()

    def _buscar_simuladas(self, termo: str, limite: int) -> list[dict[str, str]]:
        limite = max(1, min(int(limite), len(_VARIANTES)))
        html = self._html_catalogo_simulado(termo, limite)
        ofertas = self._extrair_ofertas_do_html(html)
        if not ofertas:
            ofertas = [
                {k: v for k, v in item.items() if k != "asin"}
                for item in self._ofertas_diretas(termo, limite)
            ]
        return ofertas

    def _html_catalogo_simulado(self, termo: str, limite: int) -> str:
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
        termo_titulo = " ".join(parte.capitalize() for parte in termo.split())
        semente = int(hashlib.sha256(termo.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(semente)
        preco_base = rng.uniform(79.9, 899.9)
        ofertas: list[dict[str, Any]] = []
        for indice, (rotulo, fator, _nota) in enumerate(_VARIANTES[:limite]):
            asin = _asin_ficticio(termo, indice)
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


def montar_ofertas_busca(termo: str, limite: int = 1) -> list[dict[str, str]]:
    """Monta anúncios reais: a página de busca da Amazon para o termo.

    Não inventa ASIN nem preço. O clique abre resultados ao vivo em
    amazon.com.br, já com a tag aplicada depois pelo writer/builder.
    """
    termo = (termo or "").strip()
    if not termo:
        return []
    limite = max(1, min(int(limite), 3))
    sufixos = ("", " oferta", " custo benefício")[:limite]
    ofertas: list[dict[str, str]] = []
    for sufixo in sufixos:
        consulta = f"{termo}{sufixo}".strip()
        if sufixo == "":
            nome = f"{termo[0].upper() + termo[1:]} na Amazon"
        elif "oferta" in sufixo:
            nome = f"{termo[0].upper() + termo[1:]} em oferta na Amazon"
        else:
            nome = f"{termo[0].upper() + termo[1:]} com melhor custo benefício na Amazon"
        ofertas.append(
            {
                "nome": nome,
                "preco": "Ver preço na Amazon",
                "link_original": (
                    f"{AMAZON_BASE}/s?k={quote_plus(consulta)}"
                ),
                "imagem": "",
                "tipo": "busca",
                "termo": consulta,
            }
        )
    return ofertas


def _creators_configurada() -> bool:
    return bool(
        os.getenv("AMAZON_CREDENTIAL_ID", "").strip()
        and os.getenv("AMAZON_CREDENTIAL_SECRET", "").strip()
    )


def extrair_oferta(item: dict[str, Any]) -> dict[str, str] | None:
    """Converte um item da Creators API no dicionário usado pelo builder."""
    asin = str(item.get("asin") or "").strip()
    nome = str(_dig(item, "itemInfo", "title", "displayValue") or "").strip()
    if not nome:
        return None

    link = str(item.get("detailPageURL") or "").strip()
    if not link and asin:
        link = f"{AMAZON_BASE}/dp/{asin}"
    if not link:
        return None

    imagem = _primeira_imagem(item)
    preco = _preco_do_item(item) or "Consulte o preço"
    caracteristicas = _caracteristicas(item)

    oferta: dict[str, str] = {
        "nome": nome,
        "preco": preco,
        "link_original": link,
        "imagem": imagem,
        "asin": asin,
    }
    if caracteristicas:
        oferta["caracteristicas"] = caracteristicas
    return oferta


def _itens_da_resposta(dados: dict[str, Any]) -> list[dict[str, Any]]:
    bloco = dados.get("itemsResult") or dados.get("searchResult") or {}
    itens = bloco.get("items") or dados.get("items") or []
    return [item for item in itens if isinstance(item, dict)]


def _primeira_imagem(item: dict[str, Any]) -> str:
    primario = _dig(item, "images", "primary") or {}
    if not isinstance(primario, dict):
        return ""
    for tamanho in ("hiRes", "large", "medium", "small"):
        url = _dig(primario, tamanho, "url")
        if url:
            return str(url)
    return ""


def _preco_do_item(item: dict[str, Any]) -> str:
    listings = _dig(item, "offersV2", "listings") or []
    if isinstance(listings, dict):
        listings = [listings]
    if not isinstance(listings, list) or not listings:
        return ""
    listing = listings[0] if isinstance(listings[0], dict) else {}
    preco = listing.get("price") or {}
    if not isinstance(preco, dict):
        return ""
    for chave in ("displayAmount", "display_amount"):
        valor = preco.get(chave)
        if valor:
            return str(valor)
    money = preco.get("money") or {}
    if isinstance(money, dict):
        for chave in ("displayAmount", "display_amount"):
            valor = money.get(chave)
            if valor:
                return str(valor)
        amount = money.get("amount")
        currency = money.get("currency") or money.get("currencyCode") or "BRL"
        if amount is not None and currency == "BRL":
            try:
                return _formatar_preco_brl(float(amount))
            except (TypeError, ValueError):
                return f"R$ {amount}"
        if amount is not None:
            return f"{currency} {amount}"
    return ""


def _caracteristicas(item: dict[str, Any]) -> str:
    valores = _dig(item, "itemInfo", "features", "displayValues") or []
    if isinstance(valores, str):
        return valores.strip()
    if not isinstance(valores, list):
        return ""
    limpos = [str(item_txt).strip() for item_txt in valores if str(item_txt).strip()]
    return " | ".join(limpos[:8])


def _dig(obj: Any, *chaves: str) -> Any:
    atual = obj
    for chave in chaves:
        if not isinstance(atual, dict):
            return None
        atual = atual.get(chave)
    return atual


def _cabecalho_bearer(token: str, version: str) -> str:
    if version.startswith("2."):
        return f"Bearer {token}, Version {version}"
    return f"Bearer {token}"


def _simulacao_liberada() -> bool:
    return os.getenv("ALLOW_SIMULATED", "").strip().lower() in {"1", "true", "yes", "sim"}


def _asin_ficticio(termo: str, indice: int) -> str:
    digest = hashlib.sha256(f"{termo}:{indice}".encode("utf-8")).hexdigest()
    return f"B0{digest[:8].upper()}"


def _formatar_preco_brl(valor: float) -> str:
    inteiro, centavos = f"{valor:.2f}".split(".")
    grupos: list[str] = []
    while inteiro:
        grupos.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    inteiro_fmt = ".".join(reversed(grupos))
    return f"R$ {inteiro_fmt},{centavos}"
