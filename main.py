import re
import xml.etree.ElementTree as ET
from flask import Flask, Response
import requests

app = Flask(__name__)

GOOGLE_NS = "http://base.google.com/ns/1.0"
NS = {"g": GOOGLE_NS}
FEED_CONFIG = {
    "en": {
        "source_url": "https://mixopro.store/pages/google-feed-en",
        "title": "Mixopro Google Feed(En)",
        "description": "Product feed in English for Mixopro",
    },
    "fr": {
        "source_url": "https://mixopro.store/pages/google-feed-fr",
        "title": "Mixopro Google Feed(Fr)",
        "description": "Product feed in French for Mixopro",
    },
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GoogleFeedBuilder/1.0; +https://mixopro.store)"
    )
}


def extract_rss_fragment(raw_text: str) -> str:
    rss_match = re.search(r"<rss\b.*?</rss>", raw_text, re.DOTALL | re.IGNORECASE)
    return rss_match.group(0) if rss_match else raw_text


def get_item_field_xml(item: ET.Element, tag: str) -> str:
    namespaced = item.find(f"{{{GOOGLE_NS}}}{tag}")
    if namespaced is not None and namespaced.text:
        return namespaced.text.strip()

    prefixed = item.find(f"g:{tag}", NS)
    if prefixed is not None and prefixed.text:
        return prefixed.text.strip()

    plain = item.find(tag)
    if plain is not None and plain.text:
        return plain.text.strip()

    return ""


def extract_items_with_xml(raw_text: str):
    rss_xml = extract_rss_fragment(raw_text)
    root = ET.fromstring(rss_xml)
    items = []

    for node in root.findall("./channel/item"):
        items.append(
            {
                "id": get_item_field_xml(node, "id"),
                "title": get_item_field_xml(node, "title"),
                "price": get_item_field_xml(node, "price"),
                "availability": get_item_field_xml(node, "availability"),
                "link": get_item_field_xml(node, "link"),
                "image_link": get_item_field_xml(node, "image_link"),
            }
        )

    return items


def extract_items_with_regex(raw_text: str):
    item_blocks = re.findall(r"<item\b.*?>(.*?)</item>", raw_text, re.DOTALL | re.IGNORECASE)
    items = []

    def get_tag(block: str, tag: str) -> str:
        match = re.search(
            rf"<{tag}\b[^>]*>(.*?)</{tag}>", block, re.DOTALL | re.IGNORECASE
        )
        return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(1)).strip() if match else ""

    for block in item_blocks:
        items.append(
            {
                "id": get_tag(block, "g:id"),
                "title": get_tag(block, "g:title"),
                "price": get_tag(block, "g:price"),
                "availability": get_tag(block, "g:availability"),
                "link": get_tag(block, "g:link"),
                "image_link": get_tag(block, "g:image_link"),
            }
        )

    return items


def extract_items(raw_text: str):
    try:
        return extract_items_with_xml(raw_text)
    except ET.ParseError:
        return extract_items_with_regex(raw_text)


def append_if_present(parent: ET.Element, tag: str, value: str):
    if value:
        child = ET.SubElement(parent, f"{{{GOOGLE_NS}}}{tag}")
        child.text = value


def build_google_feed_xml(items, title: str, link: str, description: str) -> str:
    ET.register_namespace("g", GOOGLE_NS)

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "description").text = description

    for item in items:
        item_node = ET.SubElement(channel, "item")
        append_if_present(item_node, "id", item.get("id", ""))
        append_if_present(item_node, "title", item.get("title", ""))
        append_if_present(item_node, "price", item.get("price", ""))
        append_if_present(item_node, "availability", item.get("availability", ""))
        append_if_present(item_node, "link", item.get("link", ""))
        append_if_present(item_node, "image_link", item.get("image_link", ""))

    return ET.tostring(rss, encoding="utf-8", xml_declaration=True).decode("utf-8")


def generate_feed(lang: str):
    config = FEED_CONFIG[lang]
    response = requests.get(config["source_url"], headers=HEADERS, timeout=60)
    response.raise_for_status()

    items = extract_items(response.text)
    xml_feed = build_google_feed_xml(
        items=items,
        title=config["title"],
        link=config["source_url"],
        description=config["description"],
    )
    return Response(xml_feed, mimetype="application/xml")


@app.route("/google-feed-en")
def google_feed_en():
    return generate_feed("en")


@app.route("/google-feed-fr")
def google_feed_fr():
    return generate_feed("fr")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
