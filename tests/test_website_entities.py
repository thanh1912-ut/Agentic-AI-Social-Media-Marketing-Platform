from services.research.website_entities import extract_jsonld_entities, parse_money, parse_public_count


def test_products_keep_decimal_price_currency_and_provenance():
    entities = extract_jsonld_entities([
        '{"@context":"https://schema.org","@type":"Product","name":"Gói Pro",'
        '"sku":"P-1","offers":[{"@type":"Offer","price":"129000.50",'
        '"priceCurrency":"VND","availability":"https://schema.org/InStock"}]}'
    ], "https://example.test/products/pro")

    assert len(entities) == 1
    product = entities[0]
    assert product["kind"] == "product"
    assert product["sku"] == "P-1"
    assert product["offers"][0]["price"] == "129000.50"
    assert product["offers"][0]["currency"] == "VND"
    assert product["offers"][0]["price_kind"] == "exact"
    assert product["offers"][0]["price_provenance"]["method"] == "json_ld"


def test_price_and_public_counts_keep_ambiguity_and_precision():
    assert parse_money("0") == "0"
    assert parse_money("1.234,50") is None

    exact = parse_public_count("69")
    approximate = parse_public_count("1,2k")
    lower_bound = parse_public_count("100+")
    fractional = parse_public_count("1.5")
    missing = parse_public_count(None)
    assert (exact.value, exact.precision) == (69, "exact")
    assert (approximate.value, approximate.precision, approximate.raw) == (None, "approximate", "1,2k")
    assert (lower_bound.value, lower_bound.lower_bound, lower_bound.precision) == (None, 100, "lower_bound")
    assert missing.missing_reason == "not_published"
    assert fractional.missing_reason == "ambiguous_public_value"


def test_articles_and_organizations_are_distinct_entities():
    entities = extract_jsonld_entities([
        '{"@graph":[{"@type":"Article","headline":"Tin mới","articleBody":"Nội dung"},'
        '{"@type":"Organization","name":"Cửa hàng","description":"Chính sách công khai"}]}'
    ], "https://example.test/news/1")
    assert [entity["kind"] for entity in entities] == ["article", "business_info"]
    assert entities[0]["content"] == "Nội dung"
    assert entities[1]["description"] == "Chính sách công khai"


def test_product_group_variants_remain_separate_priceable_products():
    entities = extract_jsonld_entities([
        '{"@type":"ProductGroup","name":"Gói học","hasVariant":['
        '{"@type":"Product","name":"Gói tháng","sku":"month",'
        '"offers":{"@type":"Offer","price":"99000","priceCurrency":"VND"}},'
        '{"@type":"Product","name":"Gói năm","sku":"year",'
        '"offers":{"@type":"Offer","price":"899000","priceCurrency":"VND"}}]}'
    ], "https://example.test/packages")
    variants = [entity for entity in entities if entity["kind"] == "product" and entity["sku"]]
    assert [(entity["title"], entity["offers"][0]["price"]) for entity in variants] == [
        ("Gói tháng", "99000"), ("Gói năm", "899000"),
    ]


def test_invalid_and_oversized_jsonld_are_ignored_with_a_bound():
    entities = extract_jsonld_entities(["{" + "x" * 100_001 + "}", "not-json"], "https://example.test/")
    assert entities == []
