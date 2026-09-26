"""Bounded, deterministic extraction of public website entities.

Only JSON data embedded as JSON-LD is parsed here. Page JavaScript is never
executed and numeric claims retain their original text and provenance.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator
from urllib.parse import urljoin


MAX_SCRIPTS = 20
MAX_SCRIPT_CHARS = 100_000
MAX_NODES = 100
MAX_OFFERS = 100
MAX_TEXT = 100_000
PARSER_VERSION = "website-entities-v2"
_COUNT = re.compile(r"^\s*([\d.,]+)\s*(k|m|nghìn|ngàn|triệu|\+)?\s*$", re.I)


@dataclass(frozen=True, slots=True)
class ParsedCount:
    value: int | None
    lower_bound: int | None
    raw: str
    precision: str | None
    missing_reason: str | None = None


def parse_public_count(raw: object) -> ParsedCount:
    """Parse obvious public counters without pretending approximations are exact."""
    if not isinstance(raw, (str, int, Decimal)) or isinstance(raw, bool):
        return ParsedCount(None, None, "", None, "not_published")
    text = str(raw).strip()
    if not text:
        return ParsedCount(None, None, "", None, "not_published")
    match = _COUNT.fullmatch(text.replace(" ", ""))
    if not match:
        return ParsedCount(None, None, text[:120], None, "unparseable_public_value")
    number, suffix = match.groups()
    suffix = (suffix or "").casefold()
    try:
        if suffix in {"k", "nghìn", "ngàn"}:
            value = int((Decimal(number.replace(",", ".")) * 1000).to_integral_value())
        elif suffix in {"m", "triệu"}:
            value = int((Decimal(number.replace(",", ".")) * 1_000_000).to_integral_value())
        else:
            normalized = number
            if "," in normalized and "." in normalized:
                normalized = normalized.replace(",", "")
            elif "," in normalized:
                left, right = normalized.rsplit(",", 1)
                normalized = left + right if len(right) == 3 else left + "." + right
            elif "." in normalized:
                left, right = normalized.rsplit(".", 1)
                normalized = left + right if len(right) == 3 else left + "." + right
            parsed_number = Decimal(normalized)
            if parsed_number != parsed_number.to_integral_value():
                return ParsedCount(None, None, text[:120], None, "ambiguous_public_value")
            value = int(parsed_number)
    except (InvalidOperation, ValueError, OverflowError):
        return ParsedCount(None, None, text[:120], None, "ambiguous_public_value")
    if value < 0 or value > 2**63 - 1:
        return ParsedCount(None, None, text[:120], None, "out_of_range")
    if suffix == "+":
        return ParsedCount(None, value, text[:120], "lower_bound")
    if suffix in {"k", "m", "nghìn", "ngàn", "triệu"}:
        return ParsedCount(None, None, text[:120], "approximate")
    return ParsedCount(value, None, text[:120], "exact")


def parse_money(value: object) -> str | None:
    """Return an unambiguous decimal string; do not infer currency or free pricing."""
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > 100:
        return None
    # JSON-LD numeric strings use a dot decimal separator. Reject localized text
    # with separators rather than silently changing the represented amount.
    if not re.fullmatch(r"\d+(?:\.\d{1,6})?", text):
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if amount < 0 or amount > Decimal("999999999999999999.999999"):
        return None
    return format(amount, "f")


def _types(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    return {str(value).rsplit("/", 1)[-1].casefold() for value in values if isinstance(value, str)}


def _nodes(document: object) -> Iterator[dict[str, Any]]:
    pending = [document]
    seen = 0
    while pending and seen < MAX_NODES:
        current = pending.pop()
        if isinstance(current, list):
            pending.extend(reversed(current[:MAX_NODES - seen]))
        elif isinstance(current, dict):
            seen += 1
            yield current
            for key in ("@graph", "itemListElement", "item", "mainEntity", "hasVariant"):
                child = current.get(key)
                if isinstance(child, (dict, list)):
                    pending.append(child)


def _scalar(value: object, limit: int = 2_000) -> str | None:
    if isinstance(value, str):
        result = " ".join(value.split())
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        result = str(value)
    elif isinstance(value, dict):
        result = _scalar(value.get("name") or value.get("@id"), limit) or ""
    elif isinstance(value, list):
        result = ", ".join(item for value_item in value[:20] if (item := _scalar(value_item, 300)))
    else:
        return None
    result = result.strip()
    return result[:limit] if result else None


def _provenance(value: Any, url: str, path: str, method: str = "json_ld") -> dict[str, Any]:
    return {"value": value, "raw_value": value, "source_url": url,
            "method": method, "locator": path}


def _offer(node: object, page_url: str, index: int, method: str = "json_ld") -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    price = node.get("price")
    currency = _scalar(node.get("priceCurrency"), 8)
    low = parse_money(node.get("lowPrice"))
    high = parse_money(node.get("highPrice"))
    amount = parse_money(price)
    kind = "unknown"
    if low is not None or high is not None:
        kind = "range" if low is not None and high is not None and low != high else "from"
    elif amount == "0":
        free_basis = _scalar(node.get("description"), 300) or ""
        if re.search(r"\b(free|miễn phí|không mất phí)\b", free_basis, re.I):
            kind = "free"
        else:
            amount = None
    elif amount is not None:
        kind = "exact"
    elif isinstance(price, str) and any(term in price.casefold() for term in ("contact", "liên hệ", "quote")):
        kind = "contact"
    elif price == 0 or price == "0":
        # A numeric zero is not enough evidence that the item is free.
        kind = "unknown"
    availability = _scalar(node.get("availability"), 120)
    seller = _scalar(node.get("seller"), 300)
    url = node.get("url")
    return {
        "identity": str(node.get("sku") or node.get("@id") or url or f"offer-{index}")[:500],
        "price_kind": kind,
        "price": amount,
        "low_price": low,
        "high_price": high,
        "currency": currency.upper() if currency else None,
        "availability": availability,
        "seller": seller,
        "url": urljoin(page_url, url) if isinstance(url, str) else page_url,
        "price_provenance": _provenance(price if price is not None else {"lowPrice": node.get("lowPrice"), "highPrice": node.get("highPrice")}, page_url, f"offers[{index}].price", method),
        "missing_reason": None if kind not in {"unknown", "contact"} else ("contact_price" if kind == "contact" else "not_published_or_ambiguous"),
    }


def extract_jsonld_entities(scripts: list[str], page_url: str) -> list[dict[str, Any]]:
    """Extract Product, Article, and business info records from bounded JSON-LD."""
    output: list[dict[str, Any]] = []
    visited = 0
    for script_index, raw in enumerate(scripts[:MAX_SCRIPTS]):
        if len(raw) > MAX_SCRIPT_CHARS:
            continue
        try:
            document = json.loads(raw)
        except (json.JSONDecodeError, RecursionError):
            continue
        for node_index, node in enumerate(_nodes(document)):
            visited += 1
            if visited > MAX_NODES:
                return output
            types = _types(node)
            source_url = node.get("url") or node.get("@id")
            if not isinstance(source_url, str):
                source_url = page_url
            entity_url = urljoin(page_url, source_url) if source_url else page_url
            if "product" in types or "productgroup" in types:
                name = _scalar(node.get("name"), 1_000)
                if not name:
                    continue
                description = _scalar(node.get("description"), MAX_TEXT)
                raw_offers = node.get("offers")
                offer_nodes = raw_offers if isinstance(raw_offers, list) else [raw_offers]
                offers = [offer for index, candidate in enumerate(offer_nodes[:MAX_OFFERS]) if (offer := _offer(candidate, entity_url, index))]
                rating = node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}
                review_count = parse_public_count(rating.get("reviewCount") or rating.get("ratingCount"))
                attributes = {}
                for prop in node.get("additionalProperty", [])[:100] if isinstance(node.get("additionalProperty"), list) else []:
                    if isinstance(prop, dict):
                        key, value = _scalar(prop.get("name"), 120), _scalar(prop.get("value"), 1_000)
                        if key and value:
                            attributes[key] = value
                sold_raw = None
                for label, value in attributes.items():
                    if re.search(r"\b(sold|sales|orders?|đã bán|lượt bán|đơn hàng)\b", label, re.I):
                        sold_raw = value
                        break
                sold_count = parse_public_count(sold_raw)
                output.append({
                    "kind": "product", "identity_url": entity_url, "title": name,
                    "category": _scalar(node.get("category"), 300),
                    "brand": _scalar(node.get("brand"), 300),
                    "sku": _scalar(node.get("sku") or node.get("productID"), 200),
                    "description": description,
                    "attributes": attributes,
                    "image_urls": [urljoin(entity_url, value) for image in (node.get("image") if isinstance(node.get("image"), list) else [node.get("image")])[:20] if (value := _scalar(image, 2048))],
                    "offers": offers,
                    "rating_value": parse_money(rating.get("ratingValue")),
                    "review_count": review_count.value,
                    "review_count_raw": review_count.raw,
                    "sold_count": sold_count.value, "sold_count_lower_bound": sold_count.lower_bound,
                    "sold_count_raw": sold_count.raw or None, "sold_precision": sold_count.precision,
                    "sold_missing_reason": sold_count.missing_reason,
                    "review_count_precision": review_count.precision,
                    "field_provenance": {
                        "title": _provenance(name, entity_url, f"$script[{script_index}].node[{node_index}].name"),
                        "sku": _provenance(node.get("sku") or node.get("productID"), entity_url, f"$script[{script_index}].node[{node_index}].sku"),
                        "description": _provenance(description, entity_url, f"$script[{script_index}].node[{node_index}].description"),
                    },
                    "extraction_method": "json_ld",
                    "variants_truncated": len(offer_nodes) > MAX_OFFERS,
                })
            elif types.intersection({"article", "newsarticle", "blogposting"}):
                title = _scalar(node.get("headline") or node.get("name"), 1_000)
                body = _scalar(node.get("articleBody") or node.get("description"), MAX_TEXT)
                if title or body:
                    output.append({"kind": "article", "identity_url": entity_url, "title": title or "",
                                  "content": body or "", "category": _scalar(node.get("articleSection"), 300),
                                  "published_at": _scalar(node.get("datePublished"), 80),
                                  "updated_at": _scalar(node.get("dateModified"), 80),
                                  "content_truncated": bool(body and len(body) >= MAX_TEXT),
                                  "field_provenance": {"title": _provenance(title, entity_url, f"$script[{script_index}].node[{node_index}].headline"),
                                                       "content": _provenance(body, entity_url, f"$script[{script_index}].node[{node_index}].articleBody")},
                                  "extraction_method": "json_ld"})
            elif types.intersection({"organization", "localbusiness", "store", "website"}):
                title = _scalar(node.get("name"), 1_000)
                description = _scalar(node.get("description"), MAX_TEXT)
                if title or description:
                    output.append({"kind": "business_info", "identity_url": entity_url,
                                  "title": title or "Thông tin website", "description": description or "",
                                  "url": entity_url,
                                  "field_provenance": {"title": _provenance(title, entity_url, f"$script[{script_index}].node[{node_index}].name"),
                                                       "description": _provenance(description, entity_url, f"$script[{script_index}].node[{node_index}].description")},
                                  "extraction_method": "json_ld"})
    return output


def extract_microdata_entities(items: list[dict[str, Any]], page_url: str) -> list[dict[str, Any]]:
    """Normalize bounded Schema.org Microdata itemscopes without reading form values."""
    output: list[dict[str, Any]] = []
    pending = list(reversed(items[:MAX_NODES]))
    visited = 0
    while pending and visited < MAX_NODES:
        node = pending.pop()
        visited += 1
        for value in node.values():
            children = value if isinstance(value, list) else [value]
            pending.extend(child for child in reversed(children[:MAX_NODES - visited]) if isinstance(child, dict))
        types = _types(node)
        source_url = _scalar(node.get("url") or node.get("@id"), 2048) or page_url
        entity_url = urljoin(page_url, source_url)
        method = "microdata"
        if "product" in types or "productgroup" in types:
            name = _scalar(node.get("name"), 1_000)
            if not name:
                continue
            raw_offers = node.get("offers")
            offer_nodes = raw_offers if isinstance(raw_offers, list) else [raw_offers]
            offers = [offer for index, candidate in enumerate(offer_nodes[:MAX_OFFERS])
                      if (offer := _offer(candidate, entity_url, index, method))]
            rating = node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}
            review_count = parse_public_count(rating.get("reviewCount") or rating.get("ratingCount"))
            properties = node.get("additionalProperty", [])
            properties = properties if isinstance(properties, list) else [properties]
            attributes = {
                key: value for prop in properties if isinstance(prop, dict)
                if (key := _scalar(prop.get("name"), 120))
                if (value := _scalar(prop.get("value"), 1_000))
            }
            sold_raw = next((value for label, value in attributes.items()
                             if re.search(r"\b(sold|sales|orders?|đã bán|lượt bán|đơn hàng)\b", label, re.I)), None)
            sold_count = parse_public_count(sold_raw)
            raw_images = node.get("image")
            raw_images = raw_images if isinstance(raw_images, list) else ([raw_images] if raw_images else [])
            output.append({
                "kind": "product", "identity_url": entity_url, "title": name,
                "category": _scalar(node.get("category"), 300),
                "brand": _scalar(node.get("brand"), 300),
                "sku": _scalar(node.get("sku") or node.get("productID"), 200),
                "description": _scalar(node.get("description"), MAX_TEXT),
                "attributes": attributes, "image_urls": [urljoin(entity_url, parsed_image)
                    for raw_image in raw_images[:20]
                    if (parsed_image := _scalar(raw_image, 2048))],
                "offers": offers, "rating_value": parse_money(rating.get("ratingValue")),
                "review_count": review_count.value, "review_count_raw": review_count.raw,
                "sold_count": sold_count.value, "sold_count_lower_bound": sold_count.lower_bound,
                "sold_count_raw": sold_count.raw or None, "sold_precision": sold_count.precision,
                "sold_missing_reason": sold_count.missing_reason,
                "review_count_precision": review_count.precision,
                "field_provenance": {
                    key: _provenance(value, entity_url, f"itemprop:{key}", method)
                    for key, value in (("title", name), ("sku", node.get("sku") or node.get("productID")),
                                       ("description", node.get("description"))) if value is not None
                },
                "extraction_method": method, "variants_truncated": len(offer_nodes) > MAX_OFFERS,
            })
        elif types.intersection({"article", "newsarticle", "blogposting"}):
            title = _scalar(node.get("headline") or node.get("name"), 1_000)
            body = _scalar(node.get("articleBody") or node.get("description"), MAX_TEXT)
            if title or body:
                output.append({
                    "kind": "article", "identity_url": entity_url, "title": title or "",
                    "content": body or "", "category": _scalar(node.get("articleSection"), 300),
                    "published_at": _scalar(node.get("datePublished"), 80),
                    "updated_at": _scalar(node.get("dateModified"), 80),
                    "content_truncated": bool(body and len(body) >= MAX_TEXT),
                    "field_provenance": {
                        key: _provenance(value, entity_url, f"itemprop:{key}", method)
                        for key, value in (("title", title), ("content", body)) if value is not None
                    },
                    "extraction_method": method,
                })
        elif types.intersection({"organization", "localbusiness", "store", "website"}):
            title = _scalar(node.get("name"), 1_000)
            description = _scalar(node.get("description"), MAX_TEXT)
            if title or description:
                output.append({
                    "kind": "business_info", "identity_url": entity_url,
                    "title": title or "Thông tin website", "description": description or "",
                    "url": entity_url,
                    "field_provenance": {
                        key: _provenance(value, entity_url, f"itemprop:{key}", method)
                        for key, value in (("title", title), ("description", description)) if value is not None
                    },
                    "extraction_method": method,
                })
    return output
