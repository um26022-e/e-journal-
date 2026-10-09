"""Builds today's edition of The E Journal (100% free: RSS + Gemini free tier)."""
import json, os, re, time, datetime, urllib.request, xml.etree.ElementTree as ET

KEY = os.environ["GEMINI_API_KEY"]
CITIES = {"Bhubaneswar": (20.2961, 85.8245), "Jaipur": (26.9124, 75.7873)}
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = datetime.datetime.now(IST)

FEEDS = {
 "world": ["https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
           "http://feeds.bbci.co.uk/news/world/rss.xml"],
 "india": ["https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
           "https://www.livemint.com/rss/news"],
 "business": ["https://www.livemint.com/rss/markets", "https://www.livemint.com/rss/companies",
              "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms"],
 "sports": ["https://timesofindia.indiatimes.com/rssfeeds/4719161.cms",
            "http://feeds.bbci.co.uk/sport/rss.xml"],
}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (E-Journal bot)"})
    return urllib.request.urlopen(req, timeout=30).read()

def pick_model():
    """Asks Google which models exist today and picks the newest normal 'flash' one."""
    if os.environ.get("GEMINI_MODEL"):
        return os.environ["GEMINI_MODEL"]
    d = json.loads(get(f"https://generativelanguage.googleapis.com/v1beta/models?key={KEY}&pageSize=200"))
    names = [m["name"].split("/")[-1] for m in d.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    print("models available:", names)
    good = [n for n in names if "flash" in n and not re.search(
        r"lite|image|tts|live|audio|preview|exp|thinking|robotics|computer|embed", n)]
    def ver(n):
        m = re.search(r"(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0
    good.sort(key=ver, reverse=True)
    return good[0] if good else (names[0] if names else "gemini-2.5-flash")

MODEL = pick_model()
print("using model:", MODEL)

def headlines(urls, n=10):
    out = []
    for u in urls:
        try:
            root = ET.fromstring(get(u))
            for it in root.iter("item"):
                t = (it.findtext("title") or "").strip()
                d = re.sub(r"<[^>]+>", "", it.findtext("description") or "").strip()[:200]
                if t: out.append(f"- {t}. {d}")
                if len([x for x in out]) >= n * len(urls): break
        except Exception as e:
            print("feed failed:", u, e)
    return "\n".join(out[:n * 2])

def weather(city, lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&current=temperature_2m&daily=temperature_2m_max,temperature_2m_min,"
           "precipitation_probability_max&timezone=Asia%2FKolkata&forecast_days=7")
    d = json.loads(get(url)); D = d["daily"]; days = []
    for i, t in enumerate(D["time"]):
        days.append([datetime.date.fromisoformat(t).strftime("%a"), round(D["temperature_2m_max"][i]),
                     round(D["temperature_2m_min"][i]), f'{D["precipitation_probability_max"][i] or 0}%'])
    rain = max(int(x[3][:-1]) for x in days[:3])
    tip = "Rain is likely in the next 3 days, carry an umbrella." if rain >= 50 else "Mostly dry for the next 3 days."
    return {"city": city, "now": f'Now {round(d["current"]["temperature_2m"])}°C',
            "hi": days[0][1], "lo": days[0][2], "tip": tip, "days": days}

history = json.load(open("jargon_history.json")) if os.path.exists("jargon_history.json") else []
news = "\n\n".join(f"[{k.upper()} HEADLINES]\n{headlines(v)}" for k, v in FEEDS.items())

prompt = f"""Today is {today:%A, %d %B %Y} in India. Below are today's headlines from Indian and
world newspapers. Using ONLY these, write ORIGINAL summaries in simple, plain English for a general
reader. Do not copy their wording. Return ONLY valid JSON of this shape:
{{"world":[{{"h":"headline","s":"2 sentence summary","w":"1-2 sentences explaining simply why it matters"}}],
"india":[...],"business":[...],"sports":[...],
"case":{{"h":"catchy question-style title","situation":"2 sentences","story":"3-4 sentences told like a friendly story with a simple analogy, in the style of Finshots","lesson":"1-2 sentences"}},
"astro":[["Aries","one short line"], ... all 12 signs in order],
"jargon":{{"term":"","means":"","formula":"","example":"","why":""}}}}
Give 3 stories each for world, india, business, sports. "case" = pick ONE business/economy situation
from the headlines. "jargon" = teach ONE basic marketing concept with a simple example in rupees; do not
use these used terms: {history}. Astro lines are light, positive and generic.

{news}"""

body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0.6}}).encode()
url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
for attempt in range(4):
    try:
        req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        r = json.load(urllib.request.urlopen(req, timeout=120))
        text = r["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text[text.index("{"): text.rindex("}") + 1]); break
    except Exception as e:
        print("attempt", attempt, "failed:", e)
        if hasattr(e, "read"): print(e.read().decode()[:500])
        time.sleep(20)
else:
    raise SystemExit("Could not build today's edition; keeping yesterday's page.")

data["date"] = f"{today:%A, %d %B %Y}"
data["note"] = "Updated automatically every morning. Summaries are AI-written from public newspaper headlines."
data["weather"] = [weather(c, *xy) for c, xy in CITIES.items()]

html = open("index.html", encoding="utf-8").read()
block = "const EDITION = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n/* ====="
html = re.sub(r"const EDITION = .*?;\n/\* =====", lambda m: block, html, count=1, flags=re.S)
open("index.html", "w", encoding="utf-8").write(html)
history.append(data["jargon"]["term"])
json.dump(history[-365:], open("jargon_history.json", "w"), indent=1)
print("Edition built for", data["date"])
