"""Expande links de afiliado que você já criou (amzn.to ou /dp/ASIN).

Só consulta as URLs passadas explicitamente — não varre a Amazon.
O CTA do post permanece o link curto original.
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})", re.I)
INTERVALO_S = 0.5


def expandir_links(urls: list[str]) -> list[dict[str, str]]:
    ofertas: list[dict[str, str]] = []
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml",
        }
    )
    for indice, bruto in enumerate(urls):
        if indice:
            time.sleep(INTERVALO_S)
        try:
            oferta = expandir_link(bruto, session=session)
        except Exception as exc:
            logger.error("Falha ao expandir %s: %s", bruto, exc)
            continue
        if oferta:
            ofertas.append(oferta)
            logger.info("Link expandido: %s → %s", bruto, oferta.get("nome"))
    return ofertas


def expandir_link(url: str, session: requests.Session | None = None) -> dict[str, str] | None:
    url = (url or "").strip()
    if not url:
        return None
    cliente = session or requests.Session()
    if session is None:
        cliente.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"})

    resposta = cliente.get(url, allow_redirects=True, timeout=TIMEOUT_SEGUNDOS)
    destino = _destino_com_asin(resposta, url)
    soup = BeautifulSoup(resposta.text or "", "html.parser") if resposta.text else None
    imagem = _extrair_imagem(soup)
    nome = _extrair_nome(soup, destino)
    if (not imagem or _nome_inutil(nome or "")) and session is not None:
        time.sleep(INTERVALO_S)
        resposta = cliente.get(destino or url, allow_redirects=True, timeout=TIMEOUT_SEGUNDOS)
        destino = _destino_com_asin(resposta, destino or url)
        soup = BeautifulSoup(resposta.text or "", "html.parser") if resposta.text else None
        imagem = imagem or _extrair_imagem(soup)
        if not nome or _nome_inutil(nome):
            nome = _extrair_nome(soup, destino)

    asin = _asin_de_url(destino)
    if not nome or _nome_inutil(nome):
        nome = _nome_do_slug(destino)
    if not nome or _nome_inutil(nome):
        logger.warning("Não achei o título em %s; pulando.", url)
        return None

    return {
        "nome": nome,
        "preco": _extrair_preco(soup) or "Ver preço na Amazon",
        "link_original": url,
        "imagem": imagem,
        "asin": asin,
        "tipo": "link_afiliado",
        "destino": destino,
    }


def eh_link_curto_afiliado(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return host.endswith("amzn.to") or host.endswith("amzn.com")


def _extrair_nome(soup: BeautifulSoup | None, destino: str) -> str:
    if soup:
        titulo = soup.select_one("#productTitle")
        if titulo:
            nome = titulo.get_text(" ", strip=True)
            if nome and not _nome_inutil(nome):
                return nome
        meta = soup.find("meta", attrs={"name": "title"})
        if meta and meta.get("content"):
            nome = _limpar_titulo_amazon(str(meta["content"]))
            if nome and not _nome_inutil(nome):
                return nome
        if soup.title and soup.title.string:
            nome = _limpar_titulo_amazon(soup.title.string)
            if nome and not _nome_inutil(nome):
                return nome
    return _nome_do_slug(destino)


def _extrair_preco(soup: BeautifulSoup | None) -> str:
    if not soup:
        return ""
    for seletor in (
        "#corePrice_feature_div .a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        ".a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
    ):
        no = soup.select_one(seletor)
        if no:
            texto = no.get_text(strip=True)
            if "R$" in texto:
                return texto
    return ""


def _extrair_imagem(soup: BeautifulSoup | None) -> str:
    if not soup:
        return ""
    img = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
    if not img:
        return ""
    for chave in ("data-old-hires", "data-a-dynamic-image", "src"):
        valor = img.get(chave) or ""
        if chave == "data-a-dynamic-image" and valor.startswith("{"):
            match = re.search(r"https://[^\"']+", valor)
            return match.group(0) if match else ""
        if isinstance(valor, str) and valor.startswith("http"):
            return valor
    return ""


def _destino_com_asin(resposta: requests.Response, original: str) -> str:
    cadeia = [original]
    cadeia.extend(item.url for item in resposta.history)
    cadeia.append(resposta.url or "")
    for candidato in reversed(cadeia):
        if _asin_de_url(candidato):
            return candidato
    return resposta.url or original


def _limpar_titulo_amazon(texto: str) -> str:
    nome = texto.strip()
    nome = re.sub(r"\s+[|:]\s+Amazon.*$", "", nome, flags=re.I).strip()
    nome = re.sub(r"^Amazon\.com\.br\s*[:|\-]\s*", "", nome, flags=re.I).strip()
    return nome


def _nome_inutil(nome: str) -> bool:
    compacto = re.sub(r"[\W_]+", "", nome, flags=re.I).lower()
    return compacto in {"amazoncombr", "amazon", "amazombr"} or len(nome.strip()) < 8


def _asin_de_url(url: str) -> str:
    achado = ASIN_RE.search(url)
    return achado.group(1).upper() if achado else ""


def _nome_do_slug(url: str) -> str:
    path = unquote(urlparse(url).path)
    partes = [p for p in path.split("/") if p and p.lower() != "dp"]
    if not partes:
        return ""
    slug = partes[0] if not ASIN_RE.search("/" + partes[0]) else (partes[0] if len(partes) == 1 else partes[0])
    if ASIN_RE.fullmatch("/" + slug) or re.fullmatch(r"[A-Z0-9]{10}", slug, re.I):
        return ""
    return slug.replace("-", " ").strip()
