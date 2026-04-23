import os
import time
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
    for attempt in range(3):
        try:
            r = requests.post(
                "https://api.dyxless.at/query",
                json={"token": DYXLESS_TOKEN, "query": phone},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            data = r.json()
            if not data.get("status") or not data.get("data"):
                return {}
            for entry in data["data"]:
                first = entry.get("first_name", "")
                last = entry.get("last_name", "")
                if first or last:
                    return {
                        "first_name": first.strip().capitalize(),
                        "last_name": last.strip().capitalize()
                    }
            return {}
        except Exception as e:
            print(f"Dyxless attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return {}

def get_contact_phone(contact_id):
    url = f"https://{AMO_DOMAIN}/api/v4/contacts/{contact_id}"
    headers = {"Authorization": f"Bearer {AMO_ACCESS_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"AMO response status: {r.status_code}")
        print(f"AMO response body: {r.text[:500]}")
        if r.status_code != 200:
            return ""
        contact = r.json()
        for field in contact.get("custom_fields_values", []) or []:
            if field.get("field_code") == "PHONE":
                vals = field.get("values", [])
                if vals:
                    return vals[0].get("value", "")
    except Exception as e:
        print(f"AMO get contact error: {e}")
    return ""

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
    try:
        r = requests.patch(url, json=payload, headers=headers, timeout=10)
        print(f"AMO update status: {r.status_code}, body: {r.text[:300]}")
        return r.json()
    except Exception as e:
        print(f"AMO update error: {e}")
        return {}

@app.route("/enrich", methods=["POST"])
def enrich():
    data = request.form
    print(f"Webhook data: {dict(data)}")

    contact_id = None
    for key in data:
        if "contacts[add][0][id]" in key or "contacts[update][0][id]" in key:
            contact_id = data[key]
            break

    if not contact_id:
        return jsonify({"error": "no contact_id"}), 400

    print(f"Contact ID: {contact_id}")

    phone = None
    for key in data:
        if "phone" in key.lower() and "value" in key.lower():
            phone = data[key]
            break

    print(f"Phone from webhook: {phone}")

    if not phone:
        time.sleep(2)
        phone = get_contact_phone(contact_id)

    print(f"Phone final: {phone}")

    if not phone:
        return jsonify({"error": "phone not found"}), 404

    info = search_by_phone(phone)
    print(f"Dyxless result: {info}")

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
