import os
import time
import requests

DYXLESS_TOKEN = "fb859acf-6a51-4ef1-a6d4-6233b7ed9694"
AMO_ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjA0OTJhOTNiODZiN2IxMmM4NTNjOTZiNGI2N2Q1MmQ4OWIzMjY4OTFlMjA3ZWU5ZmU3MGRkMTEwNmRjNjQ5ZWQ3MDI5ZDYzYWRhN2U4YmI1In0.eyJhdWQiOiJmZmEyZWM1My0xYTA5LTQ3ZGEtOTkzNi0zOGU3YjE1OThjNWUiLCJqdGkiOiIwNDkyYTkzYjg2YjdiMTJjODUzYzk2YjRiNjdkNTJkODliMzI2ODkxZTIwN2VlOWZlNzBkZDExMDZkYzY0OWVkNzAyOWQ2M2FkYTdlOGJiNSIsImlhdCI6MTc3NjkyOTAyMiwibmJmIjoxNzc2OTI5MDIyLCJleHAiOjE4ODI4Mjg4MDAsInN1YiI6IjM4NjU5OTYiLCJncmFudF90eXBlIjoiIiwiYWNjb3VudF9pZCI6NzY2MTM3MCwiYmFzZV9kb21haW4iOiJhbW9jcm0ucnUiLCJ2ZXJzaW9uIjoyLCJzY29wZXMiOlsicHVzaF9ub3RpZmljYXRpb25zIiwiZmlsZXMiLCJjcm0iLCJmaWxlc19kZWxldGUiLCJub3RpZmljYXRpb25zIl0sImhhc2hfdXVpZCI6ImJkNjQ3YTkwLTU2NTgtNGJiMi1hYmM0LTcxYWY4MjdhM2UzOCIsImFwaV9kb21haW4iOiJhcGktYi5hbW9jcm0ucnUifQ.m_0apFNVSWoVJEd0hNzfHBu_sH_71tyREK1uyuiwzU6uSqvHb3VUInioPoFcHXYXwuk-dI6vMQBxH-N6k1LVYpygir-AMGxVp-WGoJ3vezQyqbhtu5ftfNE6i2AoBKsKei5xDc7Bzt3y-TZ_z033ThSySaFUYP7fliXpD1U_WPMjolKBVefLXU4aN1CMFmFxGbD_sW_DpaoYfFjpmeV_Ndj8z-M_MCM-bwT5A9foAc_aDDgZO1mtr6Jod6Ih2gaSyV4pUb8yRB9c3V0SdZ75865awXMSPB7zb6FTgUjOz87JYlJSKcZbbNoNfFt_JB9fEkiijMnUD5t7UkzzjG--Vg"
AMO_DOMAIN = "partsela.amocrm.ru"

def clean_phone(phone):
    for ch in ["+", " ", "-", "(", ")", "\t"]:
        phone = phone.replace(ch, "")
    return phone

def search_by_phone(phone):
    phone = clean_phone(phone)
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
        print(f"Dyxless error: {e}")
        return {}

def get_contacts():
    import time as t
    since = int(t.time()) - 86400  # последние 24 часа
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
    return contacts

def update_contact(contact_id, first_name, last_name):
    headers = {
        "Authorization": f"Bearer {AMO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {}
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    r = requests.patch(
        f"https://{AMO_DOMAIN}/api/v4/contacts/{contact_id}",
        json=payload, headers=headers, timeout=10
    )
    return r.status_code

# Основной цикл
print("Загружаем контакты за последние 24 часа...")
contacts = get_contacts()
print(f"Найдено контактов: {len(contacts)}")

processed = 0
skipped = 0
found = 0

for contact in contacts:
    contact_id = contact["id"]
    first = contact.get("first_name", "").strip()
    last = contact.get("last_name", "").strip()

    if first or last:
        skipped += 1
        continue

    # Берём телефон
    phone = None
    for field in contact.get("custom_fields_values", []) or []:
        if field.get("field_code") == "PHONE":
            vals = field.get("values", [])
            if vals:
                phone = vals[0].get("value", "")
                break

    if not phone:
        skipped += 1
        continue

    print(f"[{contact_id}] Ищем по номеру {phone}...")
    info = search_by_phone(phone)

    if info:
        status = update_contact(contact_id, info.get("first_name", ""), info.get("last_name", ""))
        print(f"  → {info['first_name']} {info['last_name']} (статус {status})")
        found += 1
    else:
        print(f"  → Не найден")

    processed += 1
    time.sleep(1)  # пауза чтобы не перегрузить API

print(f"\nГотово! Обработано: {processed}, заполнено: {found}, пропущено: {skipped}")
