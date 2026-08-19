"""Orquestrador: busca ofertas, gera posts SEO e grava em ``_posts/``."""

from __future__ import annotations

import logging
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scraper import AmazonScraper  # noqa: E402
from seo_writer import aplicar_tag_afiliado, gerar_post_markdown  # noqa: E402

TIMEZONE = ZoneInfo("America/Sao_Paulo")
POSTS_DIR = ROOT_DIR / "_posts"
CONFIG_PATH = ROOT_DIR / "_config.yml"
TERMOS_PADRAO = ("air fryer", "fone bluetooth", "smartwatch")
MAX_OFERTAS_PADRAO = 3
SLUG_MAX = 80

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("builder")


def main() -> int:
    load_dotenv(ROOT_DIR / ".env")
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    config = _carregar_config()
    termos = _resolver_termos(config)
    limite = _resolver_limite(config)

    if not termos:
        logger.error("Nenhum termo de busca configurado. Abortando.")
        return 1

    scraper = AmazonScraper()
    gerados = 0
    erros = 0

    for termo in termos:
        try:
            ofertas = scraper.buscar_ofertas(termo, limite=limite)
        except Exception as exc:
            erros += 1
            logger.error("Falha ao buscar ofertas para '%s': %s", termo, exc)
            continue

        for produto in ofertas:
            try:
                if _salvar_post(produto):
                    gerados += 1
            except Exception as exc:
                erros += 1
                logger.error(
                    "Falha ao gerar post para '%s': %s",
                    produto.get("nome", termo),
                    exc,
                )

    logger.info("Concluído: %s post(s) novo(s), %s erro(s).", gerados, erros)
    return 0 if erros == 0 or gerados > 0 else 1


def _carregar_config() -> dict:
    if not CONFIG_PATH.exists():
        logger.warning("Arquivo %s não encontrado; usando padrões.", CONFIG_PATH)
        return {}
    try:
        with CONFIG_PATH.open(encoding="utf-8") as arquivo:
            dados = yaml.safe_load(arquivo) or {}
        if not isinstance(dados, dict):
            logger.warning("_config.yml não é um mapeamento YAML; ignorando.")
            return {}
        return dados
    except yaml.YAMLError as exc:
        logger.error("YAML inválido em %s: %s", CONFIG_PATH, exc)
        return {}
    except OSError as exc:
        logger.error("Não foi possível ler %s: %s", CONFIG_PATH, exc)
        return {}


def _resolver_termos(config: dict) -> list[str]:
    bruto = os.getenv("SEARCH_TERMS", "").strip()
    if bruto:
        return [item.strip() for item in bruto.split(",") if item.strip()]

    do_yaml = config.get("termos_busca") or []
    if isinstance(do_yaml, str):
        do_yaml = [do_yaml]
    termos = [str(item).strip() for item in do_yaml if str(item).strip()]
    return termos or list(TERMOS_PADRAO)


def _resolver_limite(config: dict) -> int:
    env_limite = os.getenv("MAX_OFERTAS", "").strip()
    if env_limite.isdigit():
        return max(1, int(env_limite))
    yaml_limite = config.get("max_ofertas_por_termo", MAX_OFERTAS_PADRAO)
    try:
        return max(1, int(yaml_limite))
    except (TypeError, ValueError):
        return MAX_OFERTAS_PADRAO


def _salvar_post(produto: dict) -> bool:
    nome = str(produto.get("nome") or "oferta").strip()
    slug = slugify(nome)
    hoje = datetime.now(TIMEZONE).date().isoformat()
    nome_arquivo = f"{hoje}-{slug}.md"
    destino = POSTS_DIR / nome_arquivo

    if _post_duplicado(slug):
        logger.info("Post já existe para slug '%s'; pulando para evitar conteúdo duplicado.", slug)
        return False

    tag = os.getenv("AFFILIATE_TAG", "").strip()
    produto = {
        **produto,
        "link_afiliado": aplicar_tag_afiliado(str(produto.get("link_original") or ""), tag),
    }
    corpo = gerar_post_markdown(produto)
    front_matter = _montar_front_matter(produto, corpo)
    destino.write_text(front_matter + corpo + "\n", encoding="utf-8")
    logger.info("Post salvo: %s", destino.relative_to(ROOT_DIR))
    return True


def _post_duplicado(slug: str) -> bool:
    """Evita republicar o mesmo produto em dias diferentes (conteúdo duplicado)."""
    padrao = f"*-{slug}.md"
    return any(POSTS_DIR.glob(padrao))


def _montar_front_matter(produto: dict, corpo: str) -> str:
    titulo = _extrair_h1(corpo) or produto.get("nome") or "Oferta do dia"
    descricao = _extrair_descricao(corpo)
    agora = datetime.now(TIMEZONE)
    dados = {
        "layout": "post",
        "title": titulo,
        "description": descricao,
        "date": agora.strftime("%Y-%m-%d %H:%M:%S %z"),
        "categories": ["ofertas"],
        "image": produto.get("imagem") or "",
        "preco": produto.get("preco") or "",
        "affiliate_url": produto.get("link_afiliado") or produto.get("link_original") or "",
    }
    yaml_bloco = yaml.safe_dump(
        dados,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    ).strip()
    return f"---\n{yaml_bloco}\n---\n\n"


def _extrair_h1(markdown: str) -> str:
    for linha in markdown.splitlines():
        if linha.startswith("# "):
            return linha[2:].strip()
    return ""


def _extrair_descricao(markdown: str) -> str:
    """Primeiro parágrafo útil, limitado a ~155 caracteres (meta description)."""
    paragrafos = []
    for bloco in markdown.split("\n\n"):
        texto = bloco.strip()
        if not texto or texto.startswith("#") or texto.startswith("!"):
            continue
        texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
        texto = re.sub(r"[*_`]", "", texto)
        paragrafos.append(" ".join(texto.split()))
        break
    if not paragrafos:
        return "Confira esta oferta selecionada e veja o preço atualizado."
    descricao = paragrafos[0]
    if len(descricao) <= 155:
        return descricao
    cortado = descricao[:152].rsplit(" ", 1)[0]
    return cortado + "..."


def slugify(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    ascii_txt = nfkd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_txt.lower()).strip("-")
    return (slug or "oferta")[:SLUG_MAX].strip("-")


if __name__ == "__main__":
    sys.exit(main())
