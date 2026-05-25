from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from dotenv import load_dotenv
import os, re, json, uuid, base64, random, html, csv, io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import requests

load_dotenv()

APP_VERSION = "9.0"
app = FastAPI(title="AI Shopify Agent", version=APP_VERSION)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "open-mistral-7b")
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2025-01")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

HISTORY_FILE = "generation_history.json"


@app.get("/", response_class=HTMLResponse)
def dashboard():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>AI Shopify Agent</h1><p>Backend OK. Add index.html for dashboard.</p>"


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "mistral": "LOADED" if MISTRAL_API_KEY else "MISSING",
        "mistral_model": MISTRAL_MODEL,
        "shopify_store": "LOADED" if SHOPIFY_STORE else "MISSING",
        "shopify_token": "LOADED" if SHOPIFY_ACCESS_TOKEN else "MISSING",
        "pexels": "LOADED" if PEXELS_API_KEY else "MISSING",
    }


@app.get("/history")
def history(limit: int = 50):
    items = load_history()
    return {"success": True, "count": len(items[-limit:]), "items": items[-limit:][::-1]}


@app.get("/clear-history")
def clear_history():
    save_history([])
    return {"success": True, "message": "history cleared"}


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value).strip()


def truncate(value: str, max_len: int) -> str:
    value = safe_text(value)
    return value if len(value) <= max_len else value[: max_len - 3].rstrip() + "..."


def slugify(value: str) -> str:
    value = safe_text(value).lower().replace("&", "and")
    value = re.sub(r"[^a-z0-9À-ÿ]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or uuid.uuid4().hex[:8]


def normalize_shopify_store(store: Optional[str]) -> Optional[str]:
    if not store:
        return None
    return store.strip().replace("https://", "").replace("http://", "").rstrip("/")


def shopify_headers() -> Dict[str, str]:
    return {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN or "", "Content-Type": "application/json"}


def clean_json_response(text: str) -> Dict[str, Any]:
    text = re.sub(r"```json|```", "", safe_text(text)).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("No valid JSON object found")
    return json.loads(text[start:end])


def load_history() -> List[Dict[str, Any]]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(items: List[Dict[str, Any]]) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(items[-500:], f, ensure_ascii=False, indent=2)


def append_history(item: Dict[str, Any]) -> None:
    items = load_history()
    items.append(item)
    save_history(items)


def clean_price(value: Any, niche: str = "") -> str:
    try:
        number = float(str(value).replace("€", "").replace("$", "").replace(",", ".").strip())
    except Exception:
        n = niche.lower()
        if any(x in n for x in ["skincare", "beauty", "soin"]):
            number = random.choice([34.99, 39.99, 44.99, 49.99])
        elif any(x in n for x in ["fitness", "gym", "sport"]):
            number = random.choice([49.99, 59.99, 69.99, 79.99])
        elif any(x in n for x in ["car", "auto"]):
            number = random.choice([39.99, 49.99, 59.99, 69.99])
        elif any(x in n for x in ["home", "decor", "maison"]):
            number = random.choice([39.99, 49.99, 69.99, 89.99])
        else:
            number = random.choice([39.99, 49.99, 59.99, 79.99])
    number = max(9.99, min(number, 299.99))
    return f"{number:.2f}"


def smart_compare_at_price(price: str) -> str:
    try:
        p = float(price)
        compare = int(p * random.choice([1.35, 1.45, 1.55, 1.65])) + 0.99
        return f"{max(compare, p + 15):.2f}"
    except Exception:
        return "79.99"


def generate_barcode() -> str:
    return "8" + "".join(str(random.randint(0, 9)) for _ in range(12))


def detect_category(niche: str, title: str = "") -> str:
    text = f"{niche} {title}".lower()
    if any(x in text for x in ["skincare", "beauty", "serum", "skin", "soin"]):
        return "Health & Beauty > Personal Care > Cosmetics > Skin Care"
    if any(x in text for x in ["fitness", "gym", "sport", "workout", "musculation"]):
        return "Sporting Goods > Exercise & Fitness"
    if any(x in text for x in ["kitchen", "cuisine", "cooking"]):
        return "Home & Garden > Kitchen & Dining > Kitchen Tools"
    if any(x in text for x in ["pet", "dog", "cat"]):
        return "Animals & Pet Supplies > Pet Supplies"
    if any(x in text for x in ["car", "auto", "vehicle"]):
        return "Vehicles & Parts > Vehicle Parts & Accessories"
    if any(x in text for x in ["home", "decor", "maison", "wall", "lamp"]):
        return "Home & Garden > Decor"
    return "General Merchandise"


def product_type_for(niche: str, title: str = "") -> str:
    text = f"{niche} {title}".lower()
    if "serum" in text:
        return "skincare-serum"
    if any(x in text for x in ["skincare", "beauty", "soin"]):
        return "skincare"
    if any(x in text for x in ["fitness", "gym", "sport"]):
        return "fitness"
    if any(x in text for x in ["car", "auto"]):
        return "car-accessory"
    if any(x in text for x in ["home", "decor", "lamp"]):
        return "home-decor"
    return slugify(niche)


def collection_for(niche: str, title: str = "") -> str:
    text = f"{niche} {title}".lower()
    if any(x in text for x in ["skincare", "beauty", "serum"]):
        return "Premium Skincare"
    if any(x in text for x in ["fitness", "gym", "sport"]):
        return "Fitness Essentials"
    if any(x in text for x in ["car", "auto"]):
        return "Car Accessories"
    if any(x in text for x in ["home", "decor", "lamp"]):
        return "Home & Decor"
    if any(x in text for x in ["kitchen", "cuisine"]):
        return "Kitchen Essentials"
    return f"{niche.title()} Essentials"


def image_keywords(niche: str, title: str = "", product_type: str = "") -> List[str]:
    text = f"{niche} {title} {product_type}".lower()
    if any(x in text for x in ["skincare", "serum", "beauty", "cosmetic"]):
        return ["luxury skincare product", "beauty serum bottle", "cosmetic product", "face cream product"]
    if any(x in text for x in ["fitness", "gym", "sport", "recovery"]):
        return ["fitness equipment", "gym accessories", "workout gear", "sports product"]
    if any(x in text for x in ["car", "auto", "vehicle"]):
        return ["car accessory", "automotive product", "car interior accessory"]
    if any(x in text for x in ["home", "decor", "wall", "lamp"]):
        return ["modern home decor", "interior design product", "home decoration"]
    if any(x in text for x in ["kitchen", "chef", "cooking"]):
        return ["modern kitchen gadget", "kitchen tools", "cooking accessory"]
    if any(x in text for x in ["pet", "dog", "cat"]):
        return ["pet product", "dog accessory", "cat product"]
    return [f"{niche} product", f"{niche} premium", "premium ecommerce product"]


BRAND_PREFIXES = ["Aero", "Luma", "Nova", "Velora", "Nectar", "Hydra", "Pulse", "Aura", "Zenith", "Vita", "Core", "Elixir", "Luxe", "Prisma", "Urban", "Mira"]
BRAND_SUFFIXES = ["Lab", "Works", "Studio", "Core", "Bloom", "Haus", "Forge", "Mode", "Care", "Nest", "Flow", "Supply"]


def generate_brand(niche: str) -> str:
    return random.choice(BRAND_PREFIXES) + random.choice(BRAND_SUFFIXES)


def clean_tags(tags: Any, niche: str, brand: str, product_type: str) -> List[str]:
    clean: List[str] = []
    source = tags if isinstance(tags, list) else [tags] if tags else []
    for tag in source:
        tag = re.sub(r"[^a-zA-Z0-9À-ÿ\- ]", "", safe_text(tag).lower())
        tag = re.sub(r"\s+", " ", tag).strip()
        if tag and tag not in clean:
            clean.append(tag)
    for tag in [niche, product_type, brand, "premium", "best seller", "ai generated", "shopify"]:
        tag = safe_text(tag).lower()
        if tag and tag not in clean:
            clean.append(tag)
    return clean[:20]


def clean_sku(value: Any, brand: str, niche: str, index: int) -> str:
    if value:
        sku = re.sub(r"[^A-Z0-9\-]", "-", str(value).upper())
        sku = re.sub(r"-+", "-", sku).strip("-")
        if len(sku) >= 6:
            return sku[:64]
    return f"{slugify(brand).upper()}-{slugify(niche).upper()}-{index}-{uuid.uuid4().hex[:6].upper()}"


def local_product(niche: str, index: int) -> Dict[str, Any]:
    brand = generate_brand(niche)
    pt = product_type_for(niche)
    if "skincare" in niche.lower() or "beauty" in niche.lower():
        core = random.choice(["Renewal Serum", "Hydra Glow Cream", "Radiance Essence", "Barrier Repair Oil"])
    elif "fitness" in niche.lower():
        core = random.choice(["Recovery Band", "Grip Gloves", "Performance Bottle", "Training Kit"])
    elif "car" in niche.lower():
        core = random.choice(["Drive Organizer", "Detailing Kit", "Smart Mount", "Interior Cleaner"])
    elif "home" in niche.lower() or "decor" in niche.lower():
        core = random.choice(["Wall Sconce", "Ambient Lamp", "Storage Tray", "Minimal Vase"])
    else:
        core = random.choice(["Essentials Kit", "Premium System", "Daily Set", "Performance Pack"])
    title = f"{brand} {core} {random.choice(['Pro', 'Elite', 'Max', 'Plus', 'X'])}"
    price = clean_price(None, niche)
    desc = f"""
    <h2>{html.escape(title)}</h2>
    <p><strong>{html.escape(title)}</strong> est un produit premium pensé pour la niche <strong>{html.escape(niche)}</strong>.</p>
    <p>Il combine design moderne, valeur perçue élevée et utilité concrète pour créer une fiche produit crédible et prête à vendre.</p>
    <ul>
      <li>Design professionnel et moderne</li>
      <li>Positionnement premium pour augmenter la conversion</li>
      <li>Stock configuré automatiquement</li>
      <li>Idéal pour une boutique Shopify spécialisée</li>
    </ul>
    <p><strong>Offre limitée :</strong> profitez d’un produit prêt pour le e-commerce.</p>
    """
    return {
        "brand": brand,
        "title": title,
        "description": desc,
        "price": price,
        "compare_at_price": smart_compare_at_price(price),
        "product_type": pt,
        "tags": [niche, pt, brand, "premium", "best seller"],
        "sku": clean_sku(None, brand, niche, index),
        "barcode": generate_barcode(),
        "vendor": brand,
        "handle": slugify(title),
        "seo_title": truncate(f"{title} | {niche.title()} Premium", 70),
        "seo_description": truncate(f"Découvrez {title}, un produit premium pour {niche}. Design moderne, qualité professionnelle et livraison rapide.", 160),
        "collection_name": collection_for(niche, title),
        "shopify_category": detect_category(niche, title),
        "image_query": image_keywords(niche, title, pt)[0],
        "options": [{"name": "Color", "values": ["Black", "White"]}, {"name": "Pack", "values": ["Single", "Duo"]}],
    }


def validate_product(data: Dict[str, Any], niche: str, index: int) -> Dict[str, Any]:
    fallback = local_product(niche, index)
    brand = safe_text(data.get("brand"), fallback["brand"])
    title = safe_text(data.get("title"), fallback["title"]).replace("**", "")
    title = re.sub(r"^(produit premium|premium product|produit ia|ai product)\s*\d*\s*[-–:]*\s*", "", title, flags=re.I).strip()
    if len(title) < 8:
        title = fallback["title"]
    product_type = safe_text(data.get("product_type"), product_type_for(niche, title))
    price = clean_price(data.get("price", fallback["price"]), niche)
    compare_at = clean_price(data.get("compare_at_price") or smart_compare_at_price(price), niche)
    try:
        if float(compare_at) <= float(price):
            compare_at = smart_compare_at_price(price)
    except Exception:
        compare_at = smart_compare_at_price(price)
    desc = safe_text(data.get("description"), fallback["description"])
    if "<p" not in desc and "<h" not in desc and "<ul" not in desc:
        desc = f"<h2>{html.escape(title)}</h2><p>{html.escape(desc)}</p>"
    return {
        "brand": brand[:60],
        "title": truncate(title, 120),
        "description": desc,
        "price": price,
        "compare_at_price": compare_at,
        "product_type": product_type[:80],
        "tags": clean_tags(data.get("tags", fallback["tags"]), niche, brand, product_type),
        "sku": clean_sku(data.get("sku"), brand, niche, index),
        "barcode": re.sub(r"\D", "", safe_text(data.get("barcode"), generate_barcode()))[:32],
        "vendor": safe_text(data.get("vendor"), brand)[:80],
        "handle": slugify(safe_text(data.get("handle"), title)),
        "seo_title": truncate(safe_text(data.get("seo_title"), f"{title} | {niche.title()} Premium"), 70),
        "seo_description": truncate(safe_text(data.get("seo_description"), f"Découvrez {title}, un produit premium pour {niche}. Qualité, design moderne et fiche optimisée Shopify."), 160),
        "collection_name": safe_text(data.get("collection_name"), collection_for(niche, title))[:80],
        "shopify_category": safe_text(data.get("shopify_category"), detect_category(niche, title))[:160],
        "image_query": safe_text(data.get("image_query"), image_keywords(niche, title, product_type)[0])[:120],
        "options": data.get("options") if isinstance(data.get("options"), list) else fallback["options"],
    }


def generate_product_with_mistral(niche: str, index: int) -> Dict[str, Any]:
    if not MISTRAL_API_KEY:
        return validate_product({}, niche, index)
    prompt = f"""
Tu es un expert senior Shopify, branding premium, SEO e-commerce, merchandising et conversion.

Crée UN produit Shopify ultra complet pour la niche : "{niche}".
Réponds uniquement en JSON valide. Aucun Markdown. Aucun texte autour.

Remplis : brand, title, description HTML, price, compare_at_price, product_type, tags, sku, barcode, vendor, handle, seo_title, seo_description, collection_name, shopify_category, image_query, options.
Interdit : "Produit Premium", "Produit IA", "AI Product", "Premium Product" comme titre.

Format JSON exact :
{{
  "brand": "Nom de marque court",
  "title": "Nom commercial premium",
  "description": "<h2>...</h2><p>...</p><ul><li>...</li><li>...</li><li>...</li></ul><p>...</p>",
  "price": "59.99",
  "compare_at_price": "89.99",
  "product_type": "{niche}",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "sku": "SKU-UNIQUE",
  "barcode": "1234567890123",
  "vendor": "Nom de marque",
  "handle": "handle-propre-seo",
  "seo_title": "Titre SEO max 70 caractères",
  "seo_description": "Meta description SEO max 160 caractères",
  "collection_name": "Nom collection Shopify",
  "shopify_category": "Catégorie Shopify logique",
  "image_query": "english Pexels product photo search query",
  "options": [
    {{"name": "Color", "values": ["Black", "White"]}},
    {{"name": "Pack", "values": ["Single", "Duo"]}}
  ]
}}
"""
    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
            json={"model": MISTRAL_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.55},
            timeout=120,
        )
        if r.status_code != 200:
            print("MISTRAL ERROR:", r.status_code, r.text[:500])
            return validate_product({}, niche, index)
        raw = clean_json_response(r.json()["choices"][0]["message"]["content"])
        return validate_product(raw, niche, index)
    except Exception as e:
        print("MISTRAL FALLBACK:", str(e))
        return validate_product({}, niche, index)


def get_pexels_image(product: Dict[str, Any], niche: str) -> Tuple[Optional[str], str, Optional[str]]:
    if not PEXELS_API_KEY:
        return None, "pexels_missing", None
    queries = [product.get("image_query"), *image_keywords(niche, product.get("title", ""), product.get("product_type", ""))]
    seen, unique_queries = set(), []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            unique_queries.append(q)
    for query in unique_queries:
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_API_KEY, "User-Agent": "AI-Shopify-Agent/9.0"},
                params={"query": query, "per_page": 15, "orientation": "square", "size": "large"},
                timeout=60,
            )
            if r.status_code != 200:
                print("PEXELS ERROR:", r.status_code, r.text[:300])
                continue
            photos = r.json().get("photos", [])
            if not photos:
                continue
            chosen = random.choice(photos[:10])
            src = chosen.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original") or src.get("medium")
            if url:
                return url, f"pexels:{query}", chosen.get("photographer")
        except Exception as e:
            print("PEXELS ERROR:", str(e))
    return None, "pexels_no_result", None


def download_image_as_base64(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=90, headers={"User-Agent": "Mozilla/5.0 AI-Shopify-Agent/9.0"}, allow_redirects=True)
        if r.status_code != 200 or "image" not in r.headers.get("Content-Type", "").lower():
            return None
        return base64.b64encode(r.content).decode("utf-8")
    except Exception as e:
        print("IMAGE DOWNLOAD ERROR:", str(e))
        return None


def shopify_request(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    store = normalize_shopify_store(SHOPIFY_STORE)
    if not store:
        raise ValueError("SHOPIFY_STORE missing")
    if not SHOPIFY_ACCESS_TOKEN:
        raise ValueError("SHOPIFY_ACCESS_TOKEN missing")
    url = f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/{path.lstrip('/')}"
    r = requests.request(method, url, headers=shopify_headers(), json=payload, timeout=120)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text}
    return {"status_code": r.status_code, "body": body}


def build_variants(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    colors, packs = ["Black", "White"], ["Single", "Duo"]
    try:
        for opt in product.get("options", []):
            name = safe_text(opt.get("name")).lower()
            vals = [safe_text(v) for v in opt.get("values", []) if safe_text(v)]
            if name in ["color", "colour", "couleur"] and vals:
                colors = vals[:3]
            if name in ["pack", "bundle", "lot"] and vals:
                packs = vals[:3]
    except Exception:
        pass
    base_price = float(product["price"])
    base_compare = float(product["compare_at_price"])
    variants = []
    for color in colors:
        for pack in packs:
            price, compare = base_price, base_compare
            if pack.lower() in ["duo", "2 pack", "double"]:
                price = round(base_price * 1.75, 2)
                compare = round(base_compare * 1.85, 2)
            variants.append({
                "option1": color,
                "option2": pack,
                "price": f"{price:.2f}",
                "compare_at_price": f"{compare:.2f}",
                "sku": f"{product['sku']}-{slugify(color).upper()}-{slugify(pack).upper()}",
                "barcode": generate_barcode(),
                "inventory_quantity": 100,
                "inventory_management": "shopify",
                "inventory_policy": "deny",
                "requires_shipping": True,
                "fulfillment_service": "manual",
                "taxable": True,
                "weight": 0.4,
                "weight_unit": "kg",
            })
    return variants[:9]


def create_product(product: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "product": {
            "title": product["title"],
            "body_html": product["description"],
            "vendor": product["vendor"],
            "product_type": product["product_type"],
            "status": "active",
            "handle": product["handle"],
            "tags": product["tags"],
            "published": True,
            "published_scope": "global",
            "options": [{"name": "Color"}, {"name": "Pack"}],
            "variants": build_variants(product),
            "metafields_global_title_tag": product["seo_title"],
            "metafields_global_description_tag": product["seo_description"],
        }
    }
    return shopify_request("POST", "products.json", payload)


def upload_image(product_id: int, image_b64: str, product: Dict[str, Any], photographer: Optional[str]) -> Dict[str, Any]:
    alt = truncate(f"{product['title']} - {product['product_type']} premium product" + (f" | Photo by {photographer} on Pexels" if photographer else ""), 250)
    payload = {"image": {"attachment": image_b64, "filename": f"{product['handle']}-{uuid.uuid4().hex[:8]}.jpg", "alt": alt}}
    return shopify_request("POST", f"products/{product_id}/images.json", payload)


def find_collection(title: str) -> Optional[int]:
    try:
        r = shopify_request("GET", "custom_collections.json?limit=250")
        if r["status_code"] != 200:
            return None
        for c in r["body"].get("custom_collections", []):
            if c.get("title", "").lower().strip() == title.lower().strip():
                return c.get("id")
    except Exception as e:
        print("FIND COLLECTION ERROR:", str(e))
    return None


def ensure_collection(title: str, niche: str) -> Optional[int]:
    found = find_collection(title)
    if found:
        return found
    payload = {"custom_collection": {"title": title, "body_html": f"<p>Collection automatique pour <strong>{html.escape(niche)}</strong>.</p>", "handle": slugify(title), "published": True}}
    r = shopify_request("POST", "custom_collections.json", payload)
    if r["status_code"] in [200, 201]:
        return r["body"].get("custom_collection", {}).get("id")
    print("CREATE COLLECTION ERROR:", r)
    return None


def attach_collection(product_id: int, collection_id: int) -> Dict[str, Any]:
    return shopify_request("POST", "collects.json", {"collect": {"product_id": product_id, "collection_id": collection_id}})


def logo_svg(brand: str, niche: str) -> str:
    initials = "".join([p[0].upper() for p in re.findall(r"[A-Za-z]+", brand)[:2]]) or brand[:2].upper()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512"><rect width="512" height="512" rx="120" fill="#111827"/><circle cx="256" cy="230" r="118" fill="#22c55e"/><text x="256" y="260" text-anchor="middle" font-family="Arial" font-size="120" font-weight="700" fill="white">{html.escape(initials)}</text><text x="256" y="390" text-anchor="middle" font-family="Arial" font-size="34" fill="white">{html.escape(brand[:22])}</text><text x="256" y="430" text-anchor="middle" font-family="Arial" font-size="20" fill="#d1d5db">{html.escape(niche[:30])}</text></svg>"""


def create_metafields(product_id: int, product: Dict[str, Any], image_source: str) -> List[Dict[str, Any]]:
    metafields = [
        ("ai_agent", "brand", "single_line_text_field", product["brand"]),
        ("ai_agent", "shopify_category", "single_line_text_field", product["shopify_category"]),
        ("ai_agent", "image_source", "single_line_text_field", image_source or "unknown"),
        ("ai_agent", "generated_at", "single_line_text_field", now_iso()),
        ("ai_agent", "brand_logo_svg", "multi_line_text_field", logo_svg(product["brand"], product["product_type"])),
        ("custom", "seo_title", "single_line_text_field", product["seo_title"]),
        ("custom", "seo_description", "multi_line_text_field", product["seo_description"]),
    ]
    statuses = []
    for namespace, key, field_type, value in metafields:
        try:
            r = shopify_request("POST", f"products/{product_id}/metafields.json", {"metafield": {"namespace": namespace, "key": key, "type": field_type, "value": str(value)}})
            statuses.append({"key": f"{namespace}.{key}", "status": r["status_code"], "ok": r["status_code"] in [200, 201]})
        except Exception as e:
            statuses.append({"key": f"{namespace}.{key}", "status": None, "ok": False, "error": str(e)})
    return statuses


@app.get("/generate-products")
def generate_products(niche: str = Query(..., min_length=2), count: int = Query(1, ge=1, le=50)):
    niche = safe_text(niche).lower()
    count = max(1, min(int(count), 50))
    batch_id = uuid.uuid4().hex[:12]
    results = []
    products_created = images_attached = collections_attached = metafields_written = 0

    for index in range(1, count + 1):
        result = {
            "index": index, "batch_id": batch_id, "success": False, "title": None, "brand": None,
            "product_id": None, "price": None, "compare_at_price": None, "sku": None, "barcode": None,
            "handle": None, "product_type": None, "seo_title": None, "seo_description": None,
            "collection_name": None, "collection_id": None, "collection_attached": False,
            "shopify_category": None, "image_source": None, "final_image_url": None, "image_attached": False,
            "shopify_status": None, "image_upload_status": None, "metafields_status": [], "errors": []
        }
        try:
            product = generate_product_with_mistral(niche, index)
            for k in ["title", "brand", "price", "compare_at_price", "sku", "barcode", "handle", "product_type", "seo_title", "seo_description", "collection_name", "shopify_category"]:
                result[k] = product.get(k)

            image_url, image_source, photographer = get_pexels_image(product, niche)
            result["final_image_url"], result["image_source"] = image_url, image_source
            image_b64 = download_image_as_base64(image_url)

            shop = create_product(product)
            result["shopify_status"] = shop["status_code"]
            if shop["status_code"] not in [200, 201]:
                result["errors"].append({"shopify_create_error": shop["body"]})
                results.append(result); append_history(result); continue

            product_id = shop["body"].get("product", {}).get("id")
            if not product_id:
                result["errors"].append("Shopify product created but product_id missing")
                results.append(result); append_history(result); continue

            result["product_id"] = product_id
            products_created += 1

            if image_b64:
                img = upload_image(product_id, image_b64, product, photographer)
                result["image_upload_status"] = img["status_code"]
                if img["status_code"] in [200, 201]:
                    result["image_attached"] = True; images_attached += 1
                else:
                    result["errors"].append({"image_upload_error": img["body"]})
            else:
                result["errors"].append("Pexels image missing or could not be downloaded")

            collection_id = ensure_collection(product["collection_name"], niche)
            result["collection_id"] = collection_id
            if collection_id:
                coll = attach_collection(product_id, collection_id)
                if coll["status_code"] in [200, 201]:
                    result["collection_attached"] = True; collections_attached += 1
                else:
                    result["errors"].append({"collection_attach_error": coll["body"]})
            else:
                result["errors"].append("Collection could not be created/found")

            metas = create_metafields(product_id, product, image_source or "unknown")
            result["metafields_status"] = metas
            metafields_written += sum(1 for m in metas if m.get("ok"))

            result["success"] = True
        except Exception as e:
            print("PRODUCT GENERATION ERROR:", str(e))
            result["errors"].append(str(e))
        results.append(result)
        append_history(result)

    return {
        "success": True, "version": APP_VERSION, "batch_id": batch_id, "niche": niche,
        "products_requested": count, "products_created": products_created,
        "images_attached": images_attached, "collections_attached": collections_attached,
        "metafields_written": metafields_written, "results": results,
    }

# =========================================================
# V9 SAAS / AUTOPILOT / OPERATIONS ENDPOINTS
# =========================================================

@app.get("/export-csv")
def export_csv(limit: int = 500):
    items = load_history()[-limit:]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "created_at", "batch_id", "success", "title", "brand", "product_id",
        "price", "compare_at_price", "sku", "product_type", "collection_name",
        "image_attached", "collection_attached", "errors"
    ])
    for item in items:
        writer.writerow([
            now_iso(),
            item.get("batch_id"),
            item.get("success"),
            item.get("title"),
            item.get("brand"),
            item.get("product_id"),
            item.get("price"),
            item.get("compare_at_price"),
            item.get("sku"),
            item.get("product_type"),
            item.get("collection_name"),
            item.get("image_attached"),
            item.get("collection_attached"),
            json.dumps(item.get("errors", []), ensure_ascii=False),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=shopify_agent_history.csv"},
    )


@app.get("/delete-product")
def delete_product(product_id: int):
    try:
        result = shopify_request("DELETE", f"products/{product_id}.json")
        return {
            "success": result["status_code"] in [200, 202],
            "product_id": product_id,
            "status": result["status_code"],
            "response": result["body"],
        }
    except Exception as error:
        return {"success": False, "product_id": product_id, "error": str(error)}


@app.get("/retry-failed")
def retry_failed(limit: int = 10):
    history_items = load_history()
    failed = [item for item in history_items if not item.get("success")][-limit:]
    retried = []
    for item in failed:
        niche = item.get("product_type") or item.get("collection_name") or "general"
        try:
            response = generate_products(niche=niche, count=1)
            retried.append({"original": item.get("title"), "retry": response})
        except Exception as error:
            retried.append({"original": item.get("title"), "error": str(error)})
    return {"success": True, "retried_count": len(retried), "items": retried}


@app.get("/autopilot")
def autopilot(
    niches: str = "fitness,skincare,home",
    count_per_niche: int = 3,
):
    """
    V9 autopilot:
    Example:
    /autopilot?niches=fitness,skincare,home&count_per_niche=3

    Generates products across multiple niches.
    Later this endpoint can be triggered daily by Railway cron / external scheduler.
    """
    niche_list = [n.strip().lower() for n in niches.split(",") if n.strip()]
    count_per_niche = max(1, min(int(count_per_niche), 20))

    runs = []
    total_created = 0
    total_images = 0
    total_collections = 0
    total_metafields = 0

    for niche in niche_list:
        result = generate_products(niche=niche, count=count_per_niche)
        runs.append(result)
        total_created += result.get("products_created", 0)
        total_images += result.get("images_attached", 0)
        total_collections += result.get("collections_attached", 0)
        total_metafields += result.get("metafields_written", 0)

    return {
        "success": True,
        "version": APP_VERSION,
        "mode": "autopilot",
        "niches": niche_list,
        "count_per_niche": count_per_niche,
        "total_created": total_created,
        "total_images": total_images,
        "total_collections": total_collections,
        "total_metafields": total_metafields,
        "runs": runs,
    }


@app.get("/saas-config")
def saas_config():
    """
    V9 SaaS readiness endpoint.
    This does not replace real auth/Stripe yet.
    It gives the frontend a clean config object for future user accounts, plans and quotas.
    """
    return {
        "success": True,
        "version": APP_VERSION,
        "plans": [
            {"name": "starter", "monthly_price": 19, "product_limit": 100, "bulk_limit": 10},
            {"name": "pro", "monthly_price": 49, "product_limit": 1000, "bulk_limit": 50},
            {"name": "agency", "monthly_price": 149, "product_limit": 10000, "bulk_limit": 200},
        ],
        "features": {
            "shopify_products": True,
            "pexels_images": True,
            "seo": True,
            "collections": True,
            "variants": True,
            "metafields": True,
            "history": True,
            "csv_export": True,
            "autopilot": True,
            "stripe_ready": False,
            "multi_user_ready": False,
        },
    }
