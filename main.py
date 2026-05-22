from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import requests
import os
import json
import re
import base64

load_dotenv()

app = FastAPI()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open("index.html", "r", encoding="utf-8") as file:
        return file.read()


@app.get("/health")
def health():
    return {"status": "healthy"}


def clean_json(text):
    text = re.sub(r"```json|```", "", text).strip()

    start = text.find("{")
    end = text.rfind("}") + 1

    if start != -1 and end != -1:
        text = text[start:end]

    return json.loads(text)


@app.get("/generate-products")
def generate_products(niche: str, count: int = 3):

    results = []

    for i in range(count):

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

        mistral_response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistral-small-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
        )

        if mistral_response.status_code != 200:
            results.append({
                "error": "Erreur Mistral",
                "details": mistral_response.text
            })
            continue

        response_json = mistral_response.json()

        print("MISTRAL RESPONSE:", response_json)

        content = response_json["choices"][0]["message"]["content"]

        try:
            ai_product = clean_json(content)

        except Exception as e:

            print("JSON ERROR:", str(e))

            ai_product = {
                "title": f"Produit Premium {i + 1} - {niche}",
                "description": content,
                "price": "49.99",
                "product_type": niche,
                "tags": [niche, "AI Product", "Premium"],
                "sku": f"AI-{niche.upper()}-{i + 1}"
            }

        shopify_response = requests.post(
            f"https://{SHOPIFY_STORE}/admin/api/2025-01/products.json",
            headers={
                "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "product": {
                    "title": ai_product["title"],
                    "body_html": ai_product["description"],
                    "vendor": "AI Shopify Agent",
                    "product_type": ai_product.get("product_type", niche),
                    "status": "active",
                    "tags": ai_product.get(
                        "tags",
                        [niche, "AI Product", "Premium"]
                    ),
                    "variants": [
                        {
                            "price": ai_product.get("price", "49.99"),
                            "inventory_quantity": 100,
                            "inventory_management": "shopify",
                            "sku": ai_product.get(
                                "sku",
                                f"AI-{niche.upper()}-{i + 1}"
                            )
                        }
                    ],
                    "images": [
    {
        "src": f"https://source.unsplash.com/featured/800x800/?{niche}"
                        }
                    ]
                }
            }
        )

        try:
            results.append(shopify_response.json())

        except Exception:
            results.append({
                "status_code": shopify_response.status_code,
                "text": shopify_response.text
            })

    return {
        "success": True,
        "products_created": count,
        "results": results
    }