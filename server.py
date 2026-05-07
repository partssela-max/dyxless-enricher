import os
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

DYXLESS_TOKEN = os.environ.get("DYXLESS_TOKEN")
AMO_ACCESS_TOKEN = os.environ.get("AMO_ACCESS_TOKEN")
AMO_DOMAIN = os.environ.get("AMO_DOMAIN")

DYXLESS_API_URL = "https://api.dyxless.im/query"

ATS_KEYWORDS = [
    "входящий",
    "исходящий",
    "звонок",
    "пропущен",
    "вызов"
]

DYXLESS_CACHE = {}


def normalize_phone(phone):
    if not phone:
        return ""

    digits = "".join(ch for ch in str(phone) if ch.isdigit())

    # 8XXXXXXXXXX -> 7XXXXXXXXXX
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]

    # 9308703333 -> 79308703333
    if len(digits) == 10 and digits.startswith("9"):
        digits = "7" + digits

    return digits


def dyxless_phone_variants(phone):
    normalized = normalize_phone(phone)

    if not normalized:
        return []

    variants = []

    variants.append(normalized)

    if normalized.startswith("7") and len(normalized) == 11:
        variants.append("+" + normalized)

    unique = []

    for variant in variants:
        if variant not in unique:
            unique.append(variant)

    return unique


def extract_name_from_dyxless(data):
    if not data:
        return {}

    if not data.get("status"):
        return {}

    entries = data.get("data") or []

    if not entries:
        return {}

    best = {}

    for entry in entries:
        first = entry.get("first_name", "").strip()
        last = entry.get("last_name", "").strip()

        if first and last:
            return {
                "first_name": first.capitalize(),
                "last_name": last.capitalize()
            }

        if (first or last) and not best:
            best = {
                "first_name": first.capitalize(),
                "last_name": last.capitalize()
            }

    return best


def search_by_phone(phone):
    if not DYXLESS_TOKEN:
        print("DYXLESS_TOKEN is empty")
        return {}

    phone_key = normalize_phone(phone)

    if not phone_key:
        print("Phone is empty after normalization")
        return {}

    if phone_key in DYXLESS_CACHE:
        print(f"Dyxless cache hit: {phone_key}")
        return DYXLESS_CACHE[phone_key]

    variants = dyxless_phone_variants(phone_key)

    if not variants:
        print("No Dyxless phone variants")
        DYXLESS_CACHE[phone_key] = {}
        return {}

    result = {}

    for query_phone in variants:
        print(f"Trying Dyxless query: {query_phone}")

        for attempt in range(2):
            try:
                r = requests.post(
                    DYXLESS_API_URL,
                    json={
                        "token": DYXLESS_TOKEN,
                        "query": query_phone
                    },
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0"
                    },
                    timeout=15
                )

                print(f"Dyxless status: {r.status_code}")
                print(f"Dyxless response preview: {r.text[:500]}")

                if not r.text.strip():
                    print(f"Dyxless attempt {attempt + 1} failed: empty response")
                    time.sleep(1)
                    continue

                try:
                    data = r.json()
                except Exception as e:
                    print(f"Dyxless JSON parse error: {e}")
                    print(f"Raw Dyxless response: {r.text[:1000]}")
                    time.sleep(1)
                    continue

                if r.status_code != 200:
                    print(f"Dyxless bad status: {r.status_code}, data: {data}")
                    time.sleep(1)
                    continue

                found = extract_name_from_dyxless(data)

                if found:
                    result = found
                    DYXLESS_CACHE[phone_key] = result
                    return result

                print(f"Dyxless not found for {query_phone}: {data}")
                break

            except requests.exceptions.Timeout:
                print(f"Dyxless attempt {attempt + 1} failed: timeout")
                time.sleep(1)

            except Exception as e:
                print(f"Dyxless attempt {attempt + 1} failed: {e}")
                time.sleep(1)

    DYXLESS_CACHE[phone_key] = result
    return result


def get_contact(contact_id):
    if not AMO_ACCESS_TOKEN or not AMO_DOMAIN:
        print("AMO_ACCESS_TOKEN or AMO_DOMAIN is empty")
        return None

    url = f"https://{AMO_DOMAIN}/api/v4/contacts/{contact_id}"

    headers = {
        "Authorization": f"Bearer {AMO_ACCESS_TOKEN}"
    }

    try:
        r = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        print(f"AMO get contact status: {r.status_code}")

        if r.status_code != 200:
            print(f"AMO get contact response: {r.text[:500]}")
            return None

        return r.json()

    except Exception as e:
        print(f"AMO get contact error: {e}")
        return None


def update_contact(contact_id, first_name, last_name):
    if not AMO_ACCESS_TOKEN or not AMO_DOMAIN:
        print("AMO_ACCESS_TOKEN or AMO_DOMAIN is empty")
        return 0

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

    if not payload:
        print("AMO update skipped: empty payload")
        return 0

    try:
        r = requests.patch(
            url,
            json=payload,
            headers=headers,
            timeout=10
        )

        print(f"AMO update status: {r.status_code}")
        print(f"AMO update response: {r.text[:500]}")

        return r.status_code

    except Exception as e:
        print(f"AMO update error: {e}")
        return 0


def is_ats(contact):
    if not contact:
        return False

    name = contact.get("name", "").strip().lower()
    first = contact.get("first_name", "").strip().lower()
    last = contact.get("last_name", "").strip().lower()

    text = f"{name} {first} {last}"

    return any(keyword in text for keyword in ATS_KEYWORDS)


def get_contact_phone(contact):
    if not contact:
        return ""

    for field in contact.get("custom_fields_values", []) or []:
        if field.get("field_code") == "PHONE":
            values = field.get("values", []) or []

            if values:
                return values[0].get("value", "")

    return ""


def get_contact_id_from_webhook(form_data):
    for key in form_data:
        if "contacts[add][0][id]" in key:
            return form_data[key]

        if "contacts[update][0][id]" in key:
            return form_data[key]

    return None


@app.route("/enrich", methods=["POST"])
def enrich():
    try:
        data = request.form

        contact_id = get_contact_id_from_webhook(data)

        if not contact_id:
            print("No contact_id found")
            return jsonify({
                "status": "ok",
                "msg": "no contact_id"
            }), 200

        print(f"Contact ID: {contact_id}")

        time.sleep(1)

        contact = get_contact(contact_id)

        if not contact:
            print(f"Contact {contact_id} not found")
            return jsonify({
                "status": "ok",
                "msg": "contact not found"
            }), 200

        existing_first = contact.get("first_name", "").strip()
        existing_last = contact.get("last_name", "").strip()

        if (existing_first or existing_last) and not is_ats(contact):
            print(f"Name already set: '{existing_first} {existing_last}', skipping")
            return jsonify({
                "status": "ok",
                "msg": "skipped, name already set"
            }), 200

        phone = get_contact_phone(contact)

        print(f"Phone raw: {phone}")
        print(f"Phone normalized: {normalize_phone(phone)}")

        if not phone:
            return jsonify({
                "status": "ok",
                "msg": "no phone"
            }), 200

        info = search_by_phone(phone)

        print(f"Dyxless result: {info}")

        if not info:
            return jsonify({
                "status": "ok",
                "msg": "not found in dyxless"
            }), 200

        update_status = update_contact(
            contact_id,
            info.get("first_name", ""),
            info.get("last_name", "")
        )

        return jsonify({
            "status": "ok",
            "found": info,
            "amo_update_status": update_status
        }), 200

    except Exception as e:
        print(f"Enrich error: {e}")
        return jsonify({
            "status": "ok",
            "msg": "error handled"
        }), 200


@app.route("/bulk", methods=["GET"])
def bulk():
    try:
        batch = int(request.args.get("batch", 10))
        offset = int(request.args.get("offset", 0))
        since = int(time.time()) - 86400

        if not AMO_ACCESS_TOKEN or not AMO_DOMAIN:
            return jsonify({
                "status": "error",
                "msg": "AMO_ACCESS_TOKEN or AMO_DOMAIN is empty"
            }), 200

        headers = {
            "Authorization": f"Bearer {AMO_ACCESS_TOKEN}"
        }

        contacts = []
        page = 1

        while True:
            r = requests.get(
                f"https://{AMO_DOMAIN}/api/v4/contacts",
                headers=headers,
                params={
                    "page": page,
                    "limit": 250,
                    "filter[created_at][from]": since
                },
                timeout=15
            )

            print(f"AMO bulk page {page} status: {r.status_code}")

            if r.status_code != 200:
                print(f"AMO bulk response: {r.text[:500]}")
                break

            data = r.json()

            items = data.get("_embedded", {}).get("contacts", [])

            if not items:
                break

            contacts.extend(items)

            if len(items) < 250:
                break

            page += 1

        empty_contacts = []

        for contact in contacts:
            first = contact.get("first_name", "").strip()
            last = contact.get("last_name", "").strip()

            if not first and not last:
                empty_contacts.append(contact)

        chunk = empty_contacts[offset:offset + batch]

        results = []

        for contact in chunk:
            contact_id = contact["id"]
            phone = get_contact_phone(contact)

            if not phone:
                continue

            info = search_by_phone(phone)

            if info:
                update_contact(
                    contact_id,
                    info.get("first_name", ""),
                    info.get("last_name", "")
                )

                results.append({
                    "id": contact_id,
                    "phone": phone,
                    "phone_normalized": normalize_phone(phone),
                    "name": f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
                })

            time.sleep(1)

        next_url = "done"

        if offset + batch < len(empty_contacts):
            next_url = f"/bulk?offset={offset + batch}&batch={batch}"

        return jsonify({
            "status": "ok",
            "total_contacts_loaded": len(contacts),
            "total_empty": len(empty_contacts),
            "offset": offset,
            "batch": batch,
            "processed": len(results),
            "next": next_url,
            "results": results
        }), 200

    except Exception as e:
        print(f"Bulk error: {e}")
        return jsonify({
            "status": "ok",
            "msg": "bulk error handled",
            "error": str(e)
        }), 200


@app.route("/bulk-ats", methods=["GET"])
def bulk_ats():
    try:
        batch = int(request.args.get("batch", 3))
        offset = int(request.args.get("offset", 0))

        if not AMO_ACCESS_TOKEN or not AMO_DOMAIN:
            return jsonify({
                "status": "error",
                "msg": "AMO_ACCESS_TOKEN or AMO_DOMAIN is empty"
            }), 200

        headers = {
            "Authorization": f"Bearer {AMO_ACCESS_TOKEN}"
        }

        contacts = []
        page = 1

        while True:
            r = requests.get(
                f"https://{AMO_DOMAIN}/api/v4/contacts",
                headers=headers,
                params={
                    "page": page,
                    "limit": 250
                },
                timeout=15
            )

            print(f"AMO bulk-ats page {page} status: {r.status_code}")

            if r.status_code != 200:
                print(f"AMO bulk-ats response: {r.text[:500]}")
                break

            data = r.json()

            items = data.get("_embedded", {}).get("contacts", [])

            if not items:
                break

            contacts.extend(items)

            if len(items) < 250:
                break

            page += 1

            if len(contacts) >= 500:
                break

        ats_contacts = [contact for contact in contacts if is_ats(contact)]

        chunk = ats_contacts[offset:offset + batch]

        results = []

        for contact in chunk:
            contact_id = contact["id"]
            phone = get_contact_phone(contact)

            if not phone:
                continue

            info = search_by_phone(phone)

            if info:
                update_contact(
                    contact_id,
                    info.get("first_name", ""),
                    info.get("last_name", "")
                )

                results.append({
                    "id": contact_id,
                    "phone": phone,
                    "phone_normalized": normalize_phone(phone),
                    "name": f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
                })

            time.sleep(1)

        next_url = "done"

        if offset + batch < len(ats_contacts):
            next_url = f"/bulk-ats?offset={offset + batch}&batch={batch}"

        return jsonify({
            "status": "ok",
            "total_contacts_loaded": len(contacts),
            "total_ats": len(ats_contacts),
            "offset": offset,
            "batch": batch,
            "processed": len(results),
            "next": next_url,
            "results": results
        }), 200

    except Exception as e:
        print(f"Bulk ATS error: {e}")
        return jsonify({
            "status": "ok",
            "msg": "bulk ats error handled",
            "error": str(e)
        }), 200


@app.route("/", methods=["GET", "HEAD"])
def health():
    return jsonify({
        "status": "running",
        "dyxless_token": bool(DYXLESS_TOKEN),
        "amo_access_token": bool(AMO_ACCESS_TOKEN),
        "amo_domain": bool(AMO_DOMAIN)
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
