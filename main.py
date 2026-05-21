from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import requests
import os

load_dotenv()

app = FastAPI()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open("index.html", "r", encoding="utf-8") as file:
        return file.read()


@app.get("/generate-products")
def generate_products(niche: str, count: int = 3):
    results = []

    for i in range(count):
        prompt = f"""
Crée une fiche produit Shopify premium pour la niche : {niche}

Donne :
- un nom produit unique
- une description marketing courte
- 3 bénéfices
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

        content = mistral_response.json()["choices"][0]["message"]["content"]

        shopify_response = requests.post(
            f"https://{SHOPIFY_STORE}/admin/api/2025-01/products.json",
            headers={
                "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "product": {
                    "title": f"Produit IA {i+1} - {niche}",
                    "body_html": content,
                    "vendor": "AI Shopify Agent",
                    "product_type": niche,
                    "status": "active",
                    "tags": [niche, "AI Product", "Trending", "Premium"],
                    "variants": [
                        {
                            "price": "49.99",
                            "inventory_quantity": 100,
                            "inventory_management": "shopify",
                            "sku": f"AI-{niche.upper()}-{i+1}"
                        }
                    ],
                    "images": [
                        {
                            "src": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e"
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


@app.get("/health")
def health():
    return {"status": "healthy"}