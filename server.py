import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

DYXLESS_TOKEN = os.environ.get("DYXLESS_TOKEN")
AMO_ACCESS_TOKEN = os.environ.get("AMO_ACCESS_TOKEN")
AMO_DOMAIN = os.environ.get("AMO_DOMAIN")

def clean_phone(phone):
    for ch in ["+", " ", "-", "(", ")", "\t"]:
        phone = phone.replace(ch, "")
    return phone

def search_by_phone(phone):
    phone = clean_phone(phone)
    r = requests.post(
        "https://api.dyxless.at/query",
        json={"token": DYXLESS_TOKEN, "query": phone},
        headers={"Content-Type": "application/json"},
        timeout=15
    )
    data = r.json()
    if not data.get("status") or not data.get("data"):
        return {}
    for entry in data["data"]:
        first = entry.get("first_name", "")
        last = entry.get("last_name", "")
        if first or last:
            return {"first_name": first, "last_name": last}
    return {}

def update_contact(contact_id, first_name, last_name):
    url = f"https://{AMO_DOMAIN}/api/v4/contacts/{contact_id}"
    headers = {
        "Authorization": f"Bearer {AMO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {}
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    r = requests.patch(url, json=payload, headers=headers)
    return r.json()

@app.route("/enrich", methods=["POST"])
def enrich():
    # Вебхук от AmoCRM приходит как form-data
    data = request.form

    # Извлекаем contact_id
    contact_id = None
    for key in data:
        if "contacts[add][0][id]" in key:
            contact_id = data[key]
            break
        if "contacts[update][0][id]" in key:
            contact_id = data[key]
            break

    if not contact_id:
        return jsonify({"error": "no contact_id"}), 400

    # Извлекаем телефон из вебхука
    phone = None
    for key in data:
        if "phone" in key.lower() and "value" in key.lower():
            phone = data[key]
            break

    # Если телефона нет в вебхуке — берём из API
    if not phone:
        url = f"https://{AMO_DOMAIN}/api/v4/contacts/{contact_id}"
        headers = {"Authorization": f"Bearer {AMO_ACCESS_TOKEN}"}
        r = requests.get(url, headers=headers)
        contact = r.json()
        for field in contact.get("custom_fields_values", []) or []:
            if field.get("field_code") == "PHONE":
                vals = field.get("values", [])
                if vals:
                    phone = vals[0].get("value", "")
                    break

    if not phone:
        return jsonify({"error": "phone not found"}), 404

    info = search_by_phone(phone)
    if not info:
        return jsonify({"error": "person not found"}), 404

    update_contact(contact_id, info.get("first_name", ""), info.get("last_name", ""))
    return jsonify({"status": "ok", "found": info})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
