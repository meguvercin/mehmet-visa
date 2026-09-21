#!/usr/bin/env python3
"""
visa-radar – Schengen randevu müsaitlik radarı (salt okunur)

Ne yapar : Halka açık bir agregatör API'sinden randevu durumlarını okur,
           istediğin ülke/şehir/vize tipine göre filtreler, yeni bir müsaitlik
           gördüğünde Telegram'a mesaj atar.
Ne yapmaz: VFS/iDATA/BLS sitelerine girmez, login olmaz, captcha çözmez,
           randevu almaz. Sadece haber verir; randevuyu sen resmi siteden alırsın.

Standart kütüphane dışında bağımlılık yok (pip install gerekmez).
"""
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------- ayarlar ---

def env_list(name, default):
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]

API_URLS = env_list(
    "VISA_API_URLS",
    "https://api.schengenvisaappointments.com/api/visa-list/?format=json,"
    "https://api.visasbot.com/api/visa/list",
)
SOURCE_COUNTRY = os.getenv("SOURCE_COUNTRY", "tur")          # başvurunun yapıldığı ülke
MISSION_COUNTRIES = env_list("MISSION_COUNTRIES", "che,nld,aut,svk")  # hedef ülkeler (ISO3)
CITIES = env_list("CITIES", "")                               # boş = tüm şehirler
VISA_KEYWORDS = env_list("VISA_KEYWORDS", "tourism,turizm,turist,short,kisa")  # boş = tüm tipler
STATE_FILE = os.getenv("STATE_FILE", "state.json")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
USER_AGENT = "visa-radar/1.0 (personal read-only monitor)"
TIMEOUT = 30

# API'ler bazen ISO3 kod, bazen ülke adı döndürüyor; ikisini de yakala.
COUNTRY_ALIASES = {
    "tur": {"tur", "turkey", "turkiye", "türkiye"},
    "che": {"che", "switzerland", "isvicre", "isviçre", "swiss"},
    "nld": {"nld", "netherlands", "hollanda", "holland"},
    "aut": {"aut", "austria", "avusturya"},
    "svk": {"svk", "slovakia", "slovakya"},
    "esp": {"esp", "spain", "ispanya", "i̇spanya"},
    "cze": {"cze", "czechia", "czech republic", "cekya", "çekya"},
    "hun": {"hun", "hungary", "macaristan"},
    "bgr": {"bgr", "bulgaria", "bulgaristan"},
    "grc": {"grc", "greece", "yunanistan"},
    "ita": {"ita", "italy", "italya", "i̇talya"},
    "fra": {"fra", "france", "fransa"},
    "deu": {"deu", "germany", "almanya"},
    "bel": {"bel", "belgium", "belcika", "belçika"},
    "dnk": {"dnk", "denmark", "danimarka"},
    "prt": {"prt", "portugal", "portekiz"},
    "lux": {"lux", "luxembourg", "luksemburg", "lüksemburg"},
    "rou": {"rou", "romania", "romanya"},
}

# ------------------------------------------------------------- yardımcılar ---

def norm(s):
    """küçük harf + aksan temizle (İsviçre -> isvicre)"""
    if s is None:
        return ""
    s = str(s).replace("İ", "i").replace("ı", "i")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower().strip()


def country_matches(value, wanted_codes):
    v = norm(value)
    if not v:
        return False
    for code in wanted_codes:
        code = norm(code)
        aliases = COUNTRY_ALIASES.get(code, {code})
        if v == code or v in aliases or any(a in v for a in aliases if len(a) > 3):
            return True
    return False


def first(rec, *keys):
    for k in keys:
        if k in rec and rec[k] not in (None, "", []):
            return rec[k]
    return None


def normalize_record(rec):
    """Farklı agregatör şemalarını tek forma indir."""
    date = first(rec, "appointment_date", "last_available_date", "earliest_date", "date", "next_available")
    status = first(rec, "status")
    if status is None:
        status = "open" if date else "closed"
    return {
        "source": first(rec, "source_country", "country_code", "country") or "",
        "mission": first(rec, "mission_country", "mission_code", "mission") or "",
        "center": first(rec, "center_name", "center", "centre", "location") or "",
        "visa_type": first(rec, "visa_subcategory", "visa_type", "visa_category", "category") or "",
        "date": date,
        "status": norm(status),
        "link": first(rec, "book_now_link", "link", "url") or "",
        "people": first(rec, "people_looking", "tracking_count", "watchers"),
        "checked": first(rec, "last_checked", "last_check", "updated_at"),
    }


def is_available(n):
    return n["status"] in ("open", "waitlist_open", "available") or (
        n["status"] not in ("closed", "unavailable") and bool(n["date"])
    )


def wanted(n):
    if SOURCE_COUNTRY and not country_matches(n["source"], [SOURCE_COUNTRY]):
        # bazı API'ler source alanını boş bırakıyor; boşsa eleme
        if n["source"]:
            return False
    if MISSION_COUNTRIES and not country_matches(n["mission"], MISSION_COUNTRIES):
        return False
    if CITIES and not any(norm(c) in norm(n["center"]) for c in CITIES):
        return False
    if VISA_KEYWORDS and not any(norm(k) in norm(n["visa_type"]) for k in VISA_KEYWORDS):
        return False
    return True


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # bazı API'ler {"data": [...]} bazıları doğrudan [...] döner
    if isinstance(data, dict):
        for k in ("data", "results", "items", "appointments"):
            if isinstance(data.get(k), list):
                return data[k]
        raise ValueError(f"Beklenmeyen JSON şekli: {list(data)[:5]}")
    return data


def fetch_any():
    errors = []
    for url in API_URLS:
        try:
            records = fetch_json(url)
            print(f"[ok] {url} -> {len(records)} kayıt")
            return url, records
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url}: {e}")
            print(f"[warn] {url}: {e}")
    raise RuntimeError("Hiçbir API yanıt vermedi:\n" + "\n".join(errors))


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[info] Telegram ayarlı değil, mesaj konsola yazıldı:\n" + text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = urllib.parse.urlencode(
        {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        resp.read()
    print("[ok] Telegram gönderildi")


def fmt(n):
    icon = "⏳" if n["status"] == "waitlist_open" else "✅"
    lines = [
        f"{icon} <b>Randevu durumu değişti</b>",
        f"🏢 {n['center']}",
        f"🌍 {n['source'].upper() or '?'} → {n['mission'].upper()}",
        f"📄 {n['visa_type']}",
        f"🚦 {n['status']}",
    ]
    if n["date"]:
        lines.append(f"🗓 En erken: {n['date']}")
    if n["people"] is not None:
        lines.append(f"👀 Bakan kişi: {n['people']}")
    if n["link"]:
        lines.append(f"🔗 {n['link']}")
    lines.append(f"⏰ {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}")
    return "\n".join(lines)


# ------------------------------------------------------------------ main ---

def main(argv):
    if "--test" in argv:
        telegram("🔧 visa-radar test mesajı – bot çalışıyor.")
        return 0

    url, raw = fetch_any()

    if "--dump" in argv:
        print(json.dumps(raw[:3], ensure_ascii=False, indent=2))
        print(f"... toplam {len(raw)} kayıt. Alan adlarını yukarıdan görüp gerekirse normalize_record'u güncelle.")
        return 0

    state = load_state()
    new_state = {}
    changes = []

    for rec in raw:
        n = normalize_record(rec)
        if not wanted(n):
            continue
        key = f"{norm(n['mission'])}|{norm(n['center'])}|{norm(n['visa_type'])}"
        sig = f"{n['status']}|{n['date'] or ''}"
        new_state[key] = sig
        if is_available(n) and state.get(key) != sig:
            changes.append(n)

    print(f"[info] filtreye uyan {len(new_state)} kayıt, {len(changes)} değişiklik")

    for n in changes:
        try:
            telegram(fmt(n))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] Telegram hatası: {e}")

    save_state(new_state)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
