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
            best = {}
            for entry in data["data"]:
                first = entry.get("first_name", "").strip()
                last = entry.get("last_name", "").strip()
                if first and last:
                    return {"first_name": first.capitalize(), "last_name": last.capitalize()}
                if (first or last) and not best:
                    best = {"first_name": first.capitalize(), "last_name": last.capitalize()}
            return best
        except Exception as e:
            print(f"Dyxless attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return {}

def get_contact(contact_id):
    url = f"https://{AMO_DOMAIN}/api/v4/contacts/{contact_id}"
    headers = {"Authorization": f"Bearer {AMO_ACCESS_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        print(f"AMO get contact error: {e}")
    return None

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
        print(f"AMO update status: {r.status_code}")
        return r.status_code
    except Exception as e:
        print(f"AMO update error: {e}")
        return 0

@app.route("/enrich", methods=["POST"])
def enrich():
    data = request.form
    contact_id = None
    for key in data:
        if "contacts[add][0][id]" in key or "contacts[update][0][id]" in key:
            contact_id = data[key]
            break
    if not contact_id:
        return jsonify({"error": "no contact_id"}), 400
    print(f"Contact ID: {contact_id}")
    time.sleep(1)
    contact = get_contact(contact_id)
    if not contact:
        return jsonify({"error": "contact not found"}), 404
    existing_first = contact.get("first_name", "").strip()
    existing_last = contact.get("last_name", "").strip()
    if existing_first or existing_last:
        print(f"Name already set: '{existing_first} {existing_last}', skipping")
        return jsonify({"status": "skipped"}), 200
    phone = None
    for field in contact.get("custom_fields_values", []) or []:
        if field.get("field_code") == "PHONE":
            vals = field.get("values", [])
            if vals:
                phone = vals[0].get("value", "")
                break
    print(f"Phone: {phone}")
    if not phone:
        return jsonify({"error": "phone not found"}), 404
    info = search_by_phone(phone)
    print(f"Dyxless result: {info}")
    if not info:
        return jsonify({"error": "person not found"}), 404
    update_contact(contact_id, info.get("first_name", ""), info.get("last_name", ""))
    return jsonify({"status": "ok", "found": info})

@app.route("/bulk", methods=["GET"])
def bulk():
    batch = int(request.args.get("batch", 10))
    offset = int(request.args.get("offset", 0))
    since = int(time.time()) - 86400
    headers = {"Authorization": f"Bearer {AMO_ACCESS_TOKEN}"}
    contacts = []
    page = 1
    while True:
        r = requests.get(
            f"https://{AMO_DOMAIN}/api/v4/contacts",
            headers=headers,
            params={"page": page, "limit": 250, "filter[created_at][from]": since},
            timeout=15
        )
        if r.status_code != 200:
            break
        data = r.json()
        items = data.get("_embedded", {}).get("contacts", [])
        if not items:
            break
        contacts.extend(items)
        if len(items) < 250:
            break
        page += 1

    empty = [c for c in contacts if not c.get("first_name", "").strip() and not c.get("last_name", "").strip()]
    chunk = empty[offset:offset + batch]

    results = []
    for contact in chunk:
        contact_id = contact["id"]
        phone = None
        for field in contact.get("custom_fields_values", []) or []:
            if field.get("field_code") == "PHONE":
                vals = field.get("values", [])
                if vals:
                    phone = vals[0].get("value", "")
                    break
        if not phone:
            continue
        info = search_by_phone(phone)
        if info:
            update_contact(contact_id, info.get("first_name", ""), info.get("last_name", ""))
            results.append({
                "id": contact_id,
                "phone": phone,
                "name": f"{info.get('first_name','')} {info.get('last_name','')}".strip()
            })
        time.sleep(1)

    return jsonify({
        "status": "ok",
        "total_empty": len(empty),
        "offset": offset,
        "processed": len(results),
        "next": f"/bulk?offset={offset + batch}" if offset + batch < len(empty) else "done",
        "results": results
    })

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
