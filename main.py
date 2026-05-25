from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import os
import re
import json
import uuid
import base64
import random
import requests
from typing import Any, Dict, List, Optional, Tuple

load_dotenv()

app = FastAPI(title="AI Shopify Agent", version="3.0")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "open-mistral-7b")

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2025-01")

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as file:
            return file.read()

    return """
    <html>
        <head>
            <title>AI Shopify Agent</title>
            <style>
                body { font-family: Arial, sans-serif; background: #0f0f12; color: white; padding: 50px; }
                .box { max-width: 700px; margin: auto; background: #1b1b20; padding: 35px; border-radius: 20px; }
                a { color: #00ff88; }
            </style>
        </head>
        <body>
            <div class="box">
                <h1>AI Shopify Agent 🚀</h1>
                <p>Backend running successfully.</p>
                <p><a href="/health">Health check</a></p>
                <p>Example: <code>/generate-products?niche=skincare&count=1</code></p>
            </div>
        </body>
    </html>
    """


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "version": "3.0",
        "mistral": "LOADED" if MISTRAL_API_KEY else "MISSING",
        "mistral_model": MISTRAL_MODEL,
        "shopify_store": "LOADED" if SHOPIFY_STORE else "MISSING",
        "shopify_token": "LOADED" if SHOPIFY_ACCESS_TOKEN else "MISSING",
        "pexels": "LOADED" if PEXELS_API_KEY else "MISSING",
    }


def normalize_shopify_store(store: Optional[str]) -> Optional[str]:
    if not store:
        return None
    store = store.strip().replace("https://", "").replace("http://", "").rstrip("/")
    return store


def safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value).strip()


def clean_json_response(text: str) -> Dict[str, Any]:
    text = re.sub(r"```json|```", "", text).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("No valid JSON found in AI response")
    return json.loads(text[start:end])


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9À-ÿ]+", "-", value)
    return value.strip("-") or uuid.uuid4().hex[:8]


def clean_price(value: Any, niche: str = "") -> str:
    try:
        price = str(value).replace("€", "").replace("$", "").replace(",", ".").strip()
        number = float(price)
        if number < 9:
            number = 29.99
        if number > 299:
            number = 199.99
        return f"{number:.2f}"
    except Exception:
        niche = niche.lower()
        if "skincare" in niche or "beauty" in niche:
            return "39.99"
        if "fitness" in niche or "sport" in niche:
            return "59.99"
        if "kitchen" in niche:
            return "34.99"
        if "pet" in niche:
            return "29.99"
        return "49.99"


def clean_tags(tags: Any, niche: str) -> List[str]:
    clean: List[str] = []
    if isinstance(tags, str):
        tags = [tags]
    if isinstance(tags, list):
        for tag in tags:
            tag = str(tag).strip().lower()
            tag = re.sub(r"[^a-zA-Z0-9À-ÿ\- ]", "", tag)
            tag = re.sub(r"\s+", " ", tag)
            if tag and tag not in clean:
                clean.append(tag)
    for tag in [niche.lower(), "premium", "best seller", "ai generated", "shopify"]:
        if tag not in clean:
            clean.append(tag)
    return clean[:12]


def clean_sku(sku: Any, niche: str, index: int) -> str:
    if sku:
        sku = str(sku).upper()
        sku = re.sub(r"[^A-Z0-9\-]", "-", sku)
        sku = re.sub(r"-+", "-", sku).strip("-")
        if len(sku) >= 6:
            return sku[:60]
    niche_clean = re.sub(r"[^A-Z0-9]", "-", niche.upper())
    return f"AI-{niche_clean}-{index}-{uuid.uuid4().hex[:6].upper()}"


def strip_bad_title_words(title: str) -> str:
    cleaned = title.strip().replace("**", "")
    bad_patterns = [
        r"^produit premium\s*\d*\s*[-–:]*\s*",
        r"^premium product\s*\d*\s*[-–:]*\s*",
        r"^produit ia\s*\d*\s*[-–:]*\s*",
        r"^ai product\s*\d*\s*[-–:]*\s*",
    ]
    for pattern in bad_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    return re.sub(r"\s+", " ", cleaned)


def niche_keywords(niche: str, title: str = "") -> List[str]:
    n = niche.lower()
    t = title.lower()
    if any(x in n or x in t for x in ["skincare", "beauty", "serum", "skin", "cosmetic", "soin"]):
        return ["skincare product", "beauty serum bottle", "cosmetic product", "luxury skincare", "face cream product"]
    if any(x in n or x in t for x in ["fitness", "gym", "sport", "musculation", "workout"]):
        return ["fitness equipment", "gym accessories", "workout product", "sports gear", "training equipment"]
    if any(x in n or x in t for x in ["kitchen", "cuisine", "cooking"]):
        return ["kitchen product", "modern kitchen gadget", "cooking tools", "kitchen accessory"]
    if any(x in n or x in t for x in ["pet", "dog", "cat", "animal"]):
        return ["pet product", "dog accessory", "cat product", "pet care product"]
    if any(x in n or x in t for x in ["car", "auto", "vehicle"]):
        return ["car accessory", "automotive product", "car interior accessory"]
    if any(x in n or x in t for x in ["home", "decor", "maison"]):
        return ["home decor product", "modern home accessory", "interior design product"]
    return [f"{niche} product", f"{niche} premium", f"{niche} ecommerce", "premium product"]


BRAND_PREFIXES = ["Nova", "Luma", "Nectar", "Aero", "Velora", "Hydra", "Pulse", "Aura", "Zenith", "Vita", "Core", "Elixir", "Luxe", "Prisma"]
PRODUCT_SUFFIXES = ["Pro", "Elite", "Max", "Glow", "Core", "Plus", "X", "Prime", "Studio", "Essentials", "Ultra", "Active"]


def generate_local_premium_name(niche: str, index: int) -> str:
    brand = random.choice(BRAND_PREFIXES)
    suffix = random.choice(PRODUCT_SUFFIXES)
    if "skincare" in niche.lower():
        words = ["Renewal Serum", "Hydra Glow Cream", "Radiance Oil", "Repair Essence"]
    elif "fitness" in niche.lower():
        words = ["Training Kit", "Recovery Band", "Grip Gloves", "Performance Bottle"]
    elif "kitchen" in niche.lower():
        words = ["Smart Chopper", "Chef Tool", "Storage Set", "Prep Station"]
    else:
        n = niche.strip().title()
        words = [f"{n} Kit", f"{n} Essential", f"{n} System"]
    return f"{brand} {random.choice(words)} {suffix}"


def build_fallback_product(niche: str, index: int) -> Dict[str, Any]:
    title = generate_local_premium_name(niche, index)
    description = f"""
    <h2>{title}</h2>
    <p><strong>{title}</strong> est un produit premium conçu pour la niche <strong>{niche}</strong>.</p>
    <p>Il combine design moderne, utilité réelle et positionnement e-commerce attractif pour améliorer la valeur perçue de votre boutique Shopify.</p>
    <ul>
        <li>Design professionnel et moderne</li>
        <li>Positionnement premium pour augmenter la conversion</li>
        <li>Produit adapté aux clients exigeants</li>
        <li>Idéal pour une boutique Shopify spécialisée</li>
    </ul>
    <p><strong>Offre limitée :</strong> parfait pour créer une fiche produit claire, crédible et vendable.</p>
    """
    return {
        "title": title,
        "description": description,
        "price": clean_price(None, niche),
        "product_type": niche,
        "tags": clean_tags([niche, "premium", "ecommerce"], niche),
        "sku": clean_sku(None, niche, index),
        "image_query": niche_keywords(niche, title)[0],
    }


def validate_product(product: Dict[str, Any], niche: str, index: int) -> Dict[str, Any]:
    fallback = build_fallback_product(niche, index)
    title = strip_bad_title_words(safe_text(product.get("title"), fallback["title"]))
    if len(title) < 8:
        title = fallback["title"]
    description = safe_text(product.get("description"), fallback["description"])
    if "<p" not in description and "<h" not in description and "<ul" not in description:
        description = f"<h2>{title}</h2><p>{description}</p>"
    image_query = safe_text(product.get("image_query"), "") or niche_keywords(niche, title)[0]
    return {
        "title": title[:120],
        "description": description,
        "price": clean_price(product.get("price"), niche),
        "product_type": safe_text(product.get("product_type"), niche)[:80],
        "tags": clean_tags(product.get("tags"), niche),
        "sku": clean_sku(product.get("sku"), niche, index),
        "image_query": image_query[:120],
    }


def generate_product_with_mistral(niche: str, index: int) -> Dict[str, Any]:
    if not MISTRAL_API_KEY:
        print("MISTRAL_API_KEY missing, using local fallback product")
        return build_fallback_product(niche, index)

    prompt = f"""
Tu es un expert senior en e-commerce Shopify, branding premium, copywriting et SEO.

Crée UN SEUL produit réaliste et vendable pour une boutique Shopify dans la niche : "{niche}".

Objectif :
Le produit doit avoir un vrai nom commercial, une vraie promesse marketing, un prix crédible, des tags SEO et une requête image claire.

Règles strictes :
- Réponds UNIQUEMENT en JSON valide.
- Aucun texte avant ou après le JSON.
- Pas de Markdown.
- Pas de bloc ```json.
- Interdit d'utiliser "Produit Premium", "Produit IA", "Premium Product" comme nom.
- Le nom doit ressembler à une vraie marque ou un vrai produit vendable.
- Description en HTML propre.
- Prix entre 29.99 et 199.99.
- SKU unique propre.
- image_query doit être en anglais et optimisée pour trouver une photo Pexels cohérente.

Format exact obligatoire :
{{
  "title": "Nom commercial premium du produit",
  "description": "<h2>Titre vendeur</h2><p>Description courte et persuasive.</p><ul><li>Bénéfice 1</li><li>Bénéfice 2</li><li>Bénéfice 3</li></ul><p>Phrase de conversion.</p>",
  "price": "49.99",
  "product_type": "{niche}",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "sku": "SKU-UNIQUE",
  "image_query": "english search query for a realistic product photo"
}}
"""
    try:
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
            json={"model": MISTRAL_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.65},
            timeout=120,
        )
        if response.status_code != 200:
            print("MISTRAL ERROR:", response.status_code, response.text[:500])
            return build_fallback_product(niche, index)
        content = response.json()["choices"][0]["message"]["content"]
        try:
            raw_product = clean_json_response(content)
        except Exception as error:
            print("MISTRAL JSON PARSE ERROR:", str(error))
            print("RAW AI CONTENT:", content[:500])
            raw_product = build_fallback_product(niche, index)
        return validate_product(raw_product, niche, index)
    except Exception as error:
        print("MISTRAL REQUEST ERROR:", str(error))
        return build_fallback_product(niche, index)


def get_pexels_image_url(product: Dict[str, Any], niche: str) -> Tuple[Optional[str], str]:
    queries = []
    if product.get("image_query"):
        queries.append(product["image_query"])
    queries.extend(niche_keywords(niche, product.get("title", "")))

    if not PEXELS_API_KEY:
        return None, "pexels_missing"

    for query in queries:
        try:
            response = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_API_KEY, "User-Agent": "AI-Shopify-Agent/3.0"},
                params={"query": query, "per_page": 12, "orientation": "square", "size": "large"},
                timeout=60,
            )
            if response.status_code != 200:
                print("PEXELS ERROR:", response.status_code, response.text[:300])
                continue
            photos = response.json().get("photos", [])
            if not photos:
                continue
            chosen = random.choice(photos[:8])
            src = chosen.get("src", {})
            image_url = src.get("large2x") or src.get("large") or src.get("medium") or src.get("original")
            if image_url:
                return image_url, f"pexels:{query}"
        except Exception as error:
            print("PEXELS REQUEST ERROR:", str(error))
    return None, "pexels_no_result"


def get_unsplash_fallback_url(niche: str, title: str) -> str:
    query = niche_keywords(niche, title)[0].replace(" ", ",")
    sig = uuid.uuid4().hex
    return f"https://source.unsplash.com/1200x800/?{query}&sig={sig}"


def get_best_image_url(product: Dict[str, Any], niche: str) -> Tuple[str, str]:
    pexels_url, source = get_pexels_image_url(product, niche)
    if pexels_url:
        return pexels_url, source
    return get_unsplash_fallback_url(niche, product.get("title", niche)), "unsplash_fallback"


def download_image_as_base64(url: str) -> Optional[str]:
    try:
        response = requests.get(
            url,
            timeout=90,
            headers={"User-Agent": "Mozilla/5.0 AI-Shopify-Agent/3.0", "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"},
            allow_redirects=True,
        )
        content_type = response.headers.get("Content-Type", "")
        if response.status_code != 200:
            print("IMAGE DOWNLOAD FAILED:", response.status_code, url)
            return None
        if "image" not in content_type.lower():
            print("IMAGE DOWNLOAD NOT IMAGE:", content_type, url)
            return None
        return base64.b64encode(response.content).decode("utf-8")
    except Exception as error:
        print("IMAGE DOWNLOAD ERROR:", str(error))
        return None


def shopify_headers() -> Dict[str, str]:
    return {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN or "", "Content-Type": "application/json"}


def create_shopify_product(product: Dict[str, Any]) -> Dict[str, Any]:
    store = normalize_shopify_store(SHOPIFY_STORE)
    if not store:
        raise ValueError("SHOPIFY_STORE missing")
    if not SHOPIFY_ACCESS_TOKEN:
        raise ValueError("SHOPIFY_ACCESS_TOKEN missing")
    payload = {
        "product": {
            "title": product["title"],
            "body_html": product["description"],
            "vendor": "AI Shopify Agent",
            "product_type": product["product_type"],
            "status": "active",
            "tags": product["tags"],
            "variants": [{"price": product["price"], "sku": product["sku"], "inventory_quantity": 100, "inventory_management": "shopify", "requires_shipping": True}],
            "images": [],
        }
    }
    response = requests.post(f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/products.json", headers=shopify_headers(), json=payload, timeout=120)
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}
    return {"status_code": response.status_code, "body": body}


def upload_product_image(product_id: int, image_base64: str, niche: str) -> Dict[str, Any]:
    store = normalize_shopify_store(SHOPIFY_STORE)
    if not store:
        raise ValueError("SHOPIFY_STORE missing")
    response = requests.post(
        f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/products/{product_id}/images.json",
        headers=shopify_headers(),
        json={"image": {"attachment": image_base64, "filename": f"{slugify(niche)}-{uuid.uuid4().hex[:8]}.jpg"}},
        timeout=120,
    )
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}
    return {"status_code": response.status_code, "body": body}


@app.get("/generate-products")
def generate_products(niche: str, count: int = 1):
    niche = safe_text(niche).lower()
    if not niche:
        return {"success": False, "error": "niche is required"}
    try:
        count = int(count)
    except Exception:
        count = 1
    count = max(1, min(count, 50))

    results: List[Dict[str, Any]] = []
    products_created = 0
    images_attached = 0

    for index in range(1, count + 1):
        result: Dict[str, Any] = {
            "index": index,
            "success": False,
            "title": None,
            "product_id": None,
            "price": None,
            "sku": None,
            "product_type": None,
            "image_source": None,
            "final_image_url": None,
            "image_attached": False,
            "shopify_status": None,
            "image_upload_status": None,
            "errors": [],
        }
        try:
            product = generate_product_with_mistral(niche, index)
            result["title"] = product["title"]
            result["price"] = product["price"]
            result["sku"] = product["sku"]
            result["product_type"] = product["product_type"]

            image_url, image_source = get_best_image_url(product, niche)
            result["final_image_url"] = image_url
            result["image_source"] = image_source
            image_base64 = download_image_as_base64(image_url)

            shopify_result = create_shopify_product(product)
            result["shopify_status"] = shopify_result["status_code"]
            if shopify_result["status_code"] not in [200, 201]:
                result["errors"].append({"shopify_create_error": shopify_result["body"]})
                results.append(result)
                continue

            product_id = shopify_result["body"].get("product", {}).get("id")
            if not product_id:
                result["errors"].append("Shopify product created but product_id missing")
                results.append(result)
                continue

            result["product_id"] = product_id
            products_created += 1

            if image_base64:
                image_result = upload_product_image(product_id, image_base64, niche)
                result["image_upload_status"] = image_result["status_code"]
                if image_result["status_code"] in [200, 201]:
                    result["image_attached"] = True
                    images_attached += 1
                else:
                    result["errors"].append({"image_upload_error": image_result["body"]})
            else:
                result["errors"].append("Image could not be downloaded")

            result["success"] = result["product_id"] is not None
        except Exception as error:
            print("PRODUCT GENERATION ERROR:", str(error))
            result["errors"].append(str(error))
        results.append(result)

    return {
        "success": True,
        "version": "3.0",
        "niche": niche,
        "products_requested": count,
        "products_created": products_created,
        "images_attached": images_attached,
        "results": results,
    }
