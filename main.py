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


def get_fallback_image(niche, title="product"):
    keyword = f"{niche} {title}".replace(" ", ",")
    random_id = uuid.uuid4().hex
    return f"https://source.unsplash.com/1200x800/?{keyword}&sig={random_id}"


def generate_ai_image(prompt):
    return None


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

    return response.json().get("secure_url")


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
                "model": "open-mistral-7b",
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
        except Exception:
            ai_product = {
                "title": f"Produit Premium {i + 1} - {niche}",
                "description": content,
                "price": "49.99",
                "product_type": niche,
                "tags": [niche, "AI Product", "Premium"],
                "sku": f"AI-{niche.upper()}-{i + 1}"
            }

        image_prompt = (
    f"Premium ecommerce product photography for {ai_product.get('title')} "
    f"in the {niche} niche. "
    f"Ultra realistic studio lighting, white luxury background, "
    f"professional commercial product render, highly detailed, "
    f"unique composition, modern ecommerce style, no text, no watermark."
)

        generated_image = generate_ai_image(image_prompt)

        cloudinary_image_url = None
        if generated_image:
            cloudinary_image_url = upload_to_cloudinary(generated_image)

        final_image_url = cloudinary_image_url or get_fallback_image(
    niche,
    ai_product.get("title", "product")
)

        image_attachment = None
        try:
            image_response = requests.get(final_image_url, timeout=60)
            if image_response.status_code == 200:
                image_attachment = base64.b64encode(image_response.content).decode()
        except Exception as e:
            print("IMAGE DOWNLOAD ERROR:", str(e))

        product_payload = {
            "product": {
                "title": ai_product.get("title", f"Produit IA {i + 1}"),
                "body_html": ai_product.get("description", ""),
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
                "images": []
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

        product_id = shopify_json.get("product", {}).get("id")
        image_upload_response = None

        if product_id and image_attachment:
            image_upload_response = requests.post(
                f"https://{SHOPIFY_STORE}/admin/api/2025-01/products/{product_id}/images.json",
                headers={
                    "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                    "Content-Type": "application/json"
                },
                json={
                    "image": {
                        "attachment": image_attachment,
                        "filename": f"{niche}-product.png"
                    }
                },
                timeout=120
            )

            print(
                "SHOPIFY IMAGE UPLOAD:",
                image_upload_response.status_code,
                image_upload_response.text
            )

        results.append({
            "shopify_status": shopify_response.status_code,
            "image_file_created": generated_image,
            "cloudinary_image_url": cloudinary_image_url,
            "final_image_url": final_image_url,
            "image_attached": image_attachment is not None,
            "shopify_response": shopify_json,
            "image_upload_status": image_upload_response.status_code if image_upload_response else None,
            "image_upload_response": image_upload_response.text if image_upload_response else None
        })

    return {
        "success": True,
        "products_created": count,
        "results": results
    }