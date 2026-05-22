from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import requests
import os
import json
import re
import base64
import uuid

load_dotenv()

app = FastAPI()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")

FALLBACK_IMAGES = {
    "fitness": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=1200",
    "skincare": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=1200",
    "kitchen": "https://images.unsplash.com/photo-1556911220-bff31c812dba?w=1200",
    "car": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=1200",
}


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


def get_fallback_image(niche):
    return FALLBACK_IMAGES.get(
        niche.lower(),
        "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=1200"
    )


def generate_ai_image(prompt):
    if not OPENAI_API_KEY:
        return None

    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": "1024x1024"
        },
        timeout=120
    )

    if response.status_code != 200:
        print("OPENAI IMAGE ERROR:", response.text)
        return None

    result = response.json()
    image_base64 = result["data"][0].get("b64_json")

    if not image_base64:
        print("OPENAI IMAGE ERROR: no b64_json returned")
        return None

    image_bytes = base64.b64decode(image_base64)
    file_name = f"generated_{uuid.uuid4().hex}.png"

    with open(file_name, "wb") as f:
        f.write(image_bytes)

    return file_name


def upload_to_cloudinary(file_path):
    if not CLOUDINARY_CLOUD_NAME:
        return None

    url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"

    with open(file_path, "rb") as file:
        response = requests.post(
            url,
            files={"file": file},
            data={"upload_preset": "shopify_ai"},
            timeout=120
        )

    if response.status_code != 200:
        print("CLOUDINARY ERROR:", response.text)
        return None

    data = response.json()
    print("CLOUDINARY SUCCESS:", data.get("secure_url"))

    return data.get("secure_url")


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
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=120
        )

        if mistral_response.status_code != 200:
            results.append({
                "error": "Erreur Mistral",
                "details": mistral_response.text
            })
            continue

        content = mistral_response.json()["choices"][0]["message"]["content"]

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

        image_prompt = (
            f"Professional ecommerce product photo of {ai_product['title']} "
            f"for the {niche} niche, studio lighting, white background, "
            f"premium realistic product photography, no text, no logo"
        )

        generated_image = generate_ai_image(image_prompt)

        cloudinary_image_url = None
        if generated_image:
            cloudinary_image_url = upload_to_cloudinary(generated_image)

        final_image_url = cloudinary_image_url or get_fallback_image(niche)

        product_payload = {
            "product": {
                "title": ai_product["title"],
                "body_html": ai_product["description"],
                "vendor": "AI Shopify Agent",
                "product_type": ai_product.get("product_type", niche),
                "status": "active",
                "tags": ai_product.get("tags", [niche, "AI Product", "Premium"]),
                "variants": [
                    {
                        "price": ai_product.get("price", "49.99"),
                        "inventory_quantity": 100,
                        "inventory_management": "shopify",
                        "sku": ai_product.get("sku", f"AI-{niche.upper()}-{i + 1}")
                    }
                ],
               "images": [
    {
        "attachment": base64.b64encode(
            requests.get(final_image_url).content
        ).decode()
    }
],
            }
        }

        shopify_response = requests.post(
            f"https://{SHOPIFY_STORE}/admin/api/2025-01/products.json",
            headers={
                "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json"
            },
            json=product_payload,
            timeout=120
        )

        try:
            shopify_json = shopify_response.json()
        except Exception:
            shopify_json = {"text": shopify_response.text}

        results.append({
            "shopify_status": shopify_response.status_code,
            "image_file_created": generated_image,
            "cloudinary_image_url": cloudinary_image_url,
            "final_image_url": final_image_url,
            "shopify_response": shopify_json
        })

    return {
        "success": True,
        "products_created": count,
        "results": results
    }