from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import requests
import os
import json
import re
import base64
import uuid
from typing import Any, Dict, List, Optional

load_dotenv()

app = FastAPI(title="AI Shopify Agent")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as file:
            return file.read()

    return """
    <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1>AI Shopify Agent</h1>
            <p>Backend is running.</p>
            <a href="/health">Health check</a>
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
    }


def clean_json(text: str) -> Dict[str, Any]:
    text = re.sub(r"```json|```", "", text).strip()
    start = text.find("{")
    end = text.rfind("}") + 1

    if start == -1 or end <= start:
        raise ValueError("No JSON object found")

    return json.loads(text[start:end])


def get_fallback_image(niche: str, title: str = "product") -> str:
    keyword = f"{niche} {title}".replace(" ", ",")
    random_id = uuid.uuid4().hex
    return f"https://source.unsplash.com/1200x800/?{keyword}&sig={random_id}"


def generate_ai_image(prompt: str) -> Optional[str]:
    # MVP mode: no paid image generation.
    # Later you can replace this with Replicate / Flux / OpenAI image.
    return None


def generate_product_with_mistral(niche: str, index: int) -> Dict[str, Any]:
    prompt = f"""
Tu es un expert e-commerce Shopify.

Crée 1 produit premium réaliste pour la niche : {niche}

Réponds uniquement en JSON valide, sans texte autour.

Format exact :
{{
  "title": "Nom du produit",
  "description": "Description marketing courte en HTML",
  "price": "49.99",
  "product_type": "{niche}",
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "sku": "SKU-UNIQUE"
}}
"""

    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY missing")

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "open-mistral-7b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise ValueError(f"Mistral error: {response.text}")

    content = response.json()["choices"][0]["message"]["content"]

    try:
        product = clean_json(content)
    except Exception:
        product = {
            "title": f"Produit Premium {index} - {niche}",
            "description": content,
            "price": "49.99",
            "product_type": niche,
            "tags": [niche, "AI Product", "Premium"],
            "sku": f"AI-{niche.upper()}-{index}",
        }

    product.setdefault("title", f"Produit IA {index}")
    product.setdefault("description", "")
    product.setdefault("price", "49.99")
    product.setdefault("product_type", niche)
    product.setdefault("tags", [niche, "AI Product", "Premium"])
    product.setdefault("sku", f"AI-{niche.upper()}-{index}")

    return product


def download_image_as_base64(image_url: str) -> Optional[str]:
    try:
        response = requests.get(image_url, timeout=60)
        if response.status_code != 200:
            print("IMAGE DOWNLOAD ERROR:", response.status_code, response.text[:300])
            return None

        return base64.b64encode(response.content).decode("utf-8")

    except Exception as error:
        print("IMAGE DOWNLOAD EXCEPTION:", str(error))
        return None


def create_shopify_product(product: Dict[str, Any], niche: str) -> Dict[str, Any]:
    if not SHOPIFY_STORE or not SHOPIFY_ACCESS_TOKEN:
        raise ValueError("Shopify variables missing")

    payload = {
        "product": {
            "title": product.get("title"),
            "body_html": product.get("description", ""),
            "vendor": "AI Shopify Agent",
            "product_type": product.get("product_type", niche),
            "status": "active",
            "tags": product.get("tags", []),
            "variants": [
                {
                    "price": product.get("price", "49.99"),
                    "inventory_quantity": 100,
                    "inventory_management": "shopify",
                    "sku": product.get("sku"),
                }
            ],
            "images": [],
        }
    }

    response = requests.post(
        f"https://{SHOPIFY_STORE}/admin/api/2025-01/products.json",
        headers={
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )

    try:
        body = response.json()
    except Exception:
        body = {"text": response.text}

    return {
        "status_code": response.status_code,
        "body": body,
    }


def upload_image_to_shopify(product_id: int, image_base64: str, niche: str) -> Dict[str, Any]:
    response = requests.post(
        f"https://{SHOPIFY_STORE}/admin/api/2025-01/products/{product_id}/images.json",
        headers={
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json",
        },
        json={
            "image": {
                "attachment": image_base64,
                "filename": f"{niche}-product.png",
            }
        },
        timeout=120,
    )

    try:
        body = response.json()
    except Exception:
        body = {"text": response.text}

    return {
        "status_code": response.status_code,
        "body": body,
    }


@app.get("/generate-products")
def generate_products(niche: str, count: int = 1):
    count = max(1, min(count, 50))

    results: List[Dict[str, Any]] = []
    products_created = 0

    for index in range(1, count + 1):
        item_result = {
            "index": index,
            "title": None,
            "shopify_status": None,
            "product_id": None,
            "final_image_url": None,
            "image_attached": False,
            "image_upload_status": None,
            "errors": [],
        }

        try:
            ai_product = generate_product_with_mistral(niche, index)
            item_result["title"] = ai_product.get("title")

            image_prompt = (
                f"Premium ecommerce product photography for {ai_product.get('title')} "
                f"in the {niche} niche. Ultra realistic studio lighting, white luxury background, "
                f"professional commercial product render, no text, no watermark."
            )

            generated_image = generate_ai_image(image_prompt)

            final_image_url = get_fallback_image(
                niche,
                ai_product.get("title", "product"),
            )

            item_result["final_image_url"] = final_image_url

            image_base64 = download_image_as_base64(final_image_url)

            shopify_result = create_shopify_product(ai_product, niche)
            item_result["shopify_status"] = shopify_result["status_code"]

            shopify_body = shopify_result["body"]
            product_id = shopify_body.get("product", {}).get("id")

            if not product_id:
                item_result["errors"].append(shopify_body)
                results.append(item_result)
                continue

            products_created += 1
            item_result["product_id"] = product_id

            if image_base64:
                image_upload = upload_image_to_shopify(product_id, image_base64, niche)
                item_result["image_upload_status"] = image_upload["status_code"]
                item_result["image_attached"] = image_upload["status_code"] in [200, 201]

                if not item_result["image_attached"]:
                    item_result["errors"].append(image_upload["body"])
            else:
                item_result["errors"].append("Image could not be downloaded")

        except Exception as error:
            item_result["errors"].append(str(error))

        results.append(item_result)

    return {
        "success": True,
        "products_requested": count,
        "products_created": products_created,
        "results": results,
    }