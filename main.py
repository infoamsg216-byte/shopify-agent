from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import os
import re
import json
import uuid
import base64
import requests
from typing import Any, Dict, List, Optional

load_dotenv()

app = FastAPI(title="AI Shopify Agent", version="2.0")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "open-mistral-7b")

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2025-01")


# -----------------------------
# BASIC ROUTES
# -----------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as file:
            return file.read()

    return """
    <html>
        <head>
            <title>AI Shopify Agent</title>
        </head>
        <body style="font-family:Arial;padding:40px;">
            <h1>AI Shopify Agent 🚀</h1>
            <p>Backend running successfully.</p>
            <p><a href="/health">Health check</a></p>
        </body>
    </html>
    """


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "mistral": "LOADED" if MISTRAL_API_KEY else "MISSING",
        "shopify_store": "LOADED" if SHOPIFY_STORE else "MISSING",
        "shopify_token": "LOADED" if SHOPIFY_ACCESS_TOKEN else "MISSING",
        "model": MISTRAL_MODEL,
    }


# -----------------------------
# HELPERS
# -----------------------------

def normalize_shopify_store(store: Optional[str]) -> Optional[str]:
    if not store:
        return None

    store = store.strip()
    store = store.replace("https://", "").replace("http://", "")
    store = store.rstrip("/")

    return store


def clean_json_response(text: str) -> Dict[str, Any]:
    text = re.sub(r"```json|```", "", text).strip()

    start = text.find("{")
    end = text.rfind("}") + 1

    if start == -1 or end <= start:
        raise ValueError("No valid JSON found in AI response")

    json_text = text[start:end]
    return json.loads(json_text)


def clean_price(value: Any) -> str:
    try:
        price = str(value).replace("€", "").replace("$", "").replace(",", ".").strip()
        number = float(price)
        if number < 5:
            number = 29.99
        return f"{number:.2f}"
    except Exception:
        return "49.99"


def clean_tags(tags: Any, niche: str) -> List[str]:
    if not isinstance(tags, list):
        tags = []

    clean = []

    for tag in tags:
        tag = str(tag).strip().lower()
        tag = re.sub(r"[^a-zA-Z0-9À-ÿ\- ]", "", tag)
        if tag and tag not in clean:
            clean.append(tag)

    base_tags = [
        niche.lower(),
        "ai product",
        "premium",
        "shopify",
    ]

    for tag in base_tags:
        if tag not in clean:
            clean.append(tag)

    return clean[:10]


def clean_sku(sku: Any, niche: str, index: int) -> str:
    if sku:
        sku = str(sku).upper()
        sku = re.sub(r"[^A-Z0-9\-]", "-", sku)
        return sku[:60]

    niche_clean = re.sub(r"[^A-Z0-9]", "-", niche.upper())
    return f"AI-{niche_clean}-{index}-{uuid.uuid4().hex[:6].upper()}"


def build_fallback_product(niche: str, index: int) -> Dict[str, Any]:
    title = f"Produit Premium {index} - {niche.title()}"

    return {
        "title": title,
        "description": f"""
        <h2>{title}</h2>
        <p>Produit premium sélectionné pour la niche <strong>{niche}</strong>.</p>
        <p>Conçu pour offrir une excellente expérience client, avec un positionnement moderne, fiable et adapté à une boutique Shopify professionnelle.</p>
        <ul>
            <li>Qualité premium</li>
            <li>Design moderne</li>
            <li>Idéal pour les clients exigeants</li>
            <li>Parfait pour une boutique e-commerce</li>
        </ul>
        """,
        "price": "49.99",
        "product_type": niche,
        "tags": [niche, "premium", "ai product", "shopify"],
        "sku": clean_sku(None, niche, index),
    }


def validate_product(product: Dict[str, Any], niche: str, index: int) -> Dict[str, Any]:
    fallback = build_fallback_product(niche, index)

    title = str(product.get("title") or fallback["title"]).strip()
    title = re.sub(r"\s+", " ", title)

    description = str(product.get("description") or fallback["description"]).strip()

    if "<p" not in description and "<h" not in description:
        description = f"<p>{description}</p>"

    return {
        "title": title[:120],
        "description": description,
        "price": clean_price(product.get("price", "49.99")),
        "product_type": str(product.get("product_type") or niche).strip(),
        "tags": clean_tags(product.get("tags"), niche),
        "sku": clean_sku(product.get("sku"), niche, index),
    }


def get_fallback_image_url(niche: str, title: str) -> str:
    query = f"{niche} {title}".replace(" ", ",")
    sig = uuid.uuid4().hex
    return f"https://source.unsplash.com/1200x800/?{query}&sig={sig}"


def download_image_as_base64(url: str) -> Optional[str]:
    try:
        response = requests.get(
            url,
            timeout=60,
            headers={
                "User-Agent": "Mozilla/5.0 AI-Shopify-Agent"
            }
        )

        if response.status_code != 200:
            print("IMAGE DOWNLOAD FAILED:", response.status_code)
            return None

        return base64.b64encode(response.content).decode("utf-8")

    except Exception as error:
        print("IMAGE DOWNLOAD ERROR:", str(error))
        return None


# -----------------------------
# AI GENERATION
# -----------------------------

def generate_product_with_mistral(niche: str, index: int) -> Dict[str, Any]:
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY missing")

    prompt = f"""
Tu es un expert e-commerce Shopify, branding, dropshipping premium et copywriting.

Ta mission :
Créer UN produit Shopify réaliste, vendable, premium, cohérent avec la niche suivante : "{niche}".

Règles importantes :
- Réponds uniquement en JSON valide.
- Aucun texte avant ou après.
- Pas de Markdown.
- Pas de ```json.
- Produit crédible, pas générique.
- Nom court, commercial, propre.
- Description en HTML propre.
- Prix réaliste entre 29.99 et 199.99.
- SKU unique et propre.
- Tags SEO propres.

Format exact obligatoire :
{{
  "title": "Nom commercial du produit",
  "description": "<h2>...</h2><p>...</p><ul><li>...</li></ul>",
  "price": "49.99",
  "product_type": "{niche}",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "sku": "SKU-UNIQUE"
}}
"""

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0.75,
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise ValueError(f"Mistral error {response.status_code}: {response.text}")

    content = response.json()["choices"][0]["message"]["content"]

    try:
        raw_product = clean_json_response(content)
    except Exception as error:
        print("JSON PARSE ERROR:", str(error))
        print("RAW AI CONTENT:", content[:500])
        raw_product = build_fallback_product(niche, index)

    return validate_product(raw_product, niche, index)


# -----------------------------
# SHOPIFY
# -----------------------------

def shopify_headers() -> Dict[str, str]:
    return {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN or "",
        "Content-Type": "application/json",
    }


def create_shopify_product(product: Dict[str, Any], niche: str) -> Dict[str, Any]:
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
            "variants": [
                {
                    "price": product["price"],
                    "sku": product["sku"],
                    "inventory_quantity": 100,
                    "inventory_management": "shopify",
                    "requires_shipping": True,
                }
            ],
            "images": [],
        }
    }

    url = f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/products.json"

    response = requests.post(
        url,
        headers=shopify_headers(),
        json=payload,
        timeout=120,
    )

    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}

    return {
        "status_code": response.status_code,
        "body": body,
    }


def upload_product_image(product_id: int, image_base64: str, niche: str) -> Dict[str, Any]:
    store = normalize_shopify_store(SHOPIFY_STORE)

    url = f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/products/{product_id}/images.json"

    response = requests.post(
        url,
        headers=shopify_headers(),
        json={
            "image": {
                "attachment": image_base64,
                "filename": f"{niche.replace(' ', '-')}-{uuid.uuid4().hex[:8]}.png",
            }
        },
        timeout=120,
    )

    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}

    return {
        "status_code": response.status_code,
        "body": body,
    }


# -----------------------------
# MAIN API
# -----------------------------

@app.get("/generate-products")
def generate_products(niche: str, count: int = 1):
    niche = niche.strip().lower()
    count = max(1, min(int(count), 50))

    results = []
    products_created = 0
    images_attached = 0

    for index in range(1, count + 1):
        result = {
            "index": index,
            "success": False,
            "title": None,
            "product_id": None,
            "price": None,
            "sku": None,
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

            image_url = get_fallback_image_url(niche, product["title"])
            result["final_image_url"] = image_url

            image_base64 = download_image_as_base64(image_url)

            shopify_result = create_shopify_product(product, niche)
            result["shopify_status"] = shopify_result["status_code"]

            if shopify_result["status_code"] not in [200, 201]:
                result["errors"].append({
                    "shopify_create_error": shopify_result["body"]
                })
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
                    result["errors"].append({
                        "image_upload_error": image_result["body"]
                    })
            else:
                result["errors"].append("Image fallback could not be downloaded")

            result["success"] = True

        except Exception as error:
            result["errors"].append(str(error))

        results.append(result)

    return {
        "success": True,
        "niche": niche,
        "products_requested": count,
        "products_created": products_created,
        "images_attached": images_attached,
        "results": results,
    }