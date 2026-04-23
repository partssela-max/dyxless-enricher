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

def get_contact(contact_id):
    url = f"https://{AMO_DOMAIN}/api/v4/contacts/{contact_id}"
    headers = {"Authorization": f"Bearer {AMO_ACCESS_TOKEN}"}
    r = requests.get(url, headers=headers)
    return r.json()

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
    body = request.json or {}
    contact_id = body.get("contact_id")
    phone = body.get("phone")

    if not contact_id:
        return jsonify({"error": "contact_id required"}), 400

    if not phone:
        contact = get_contact(int(contact_id))
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
        return jsonify({"error": "person not found", "phone": phone}), 404

    result = update_contact(int(contact_id), info.get("first_name", ""), info.get("last_name", ""))
    return jsonify({"status": "ok", "found": info})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
