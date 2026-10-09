"""Builds today's edition of The E Journal and injects it into index.html."""
import json, os, re, datetime, urllib.request
import anthropic

CITIES = {"Bhubaneswar": (20.2961, 85.8245), "Jaipur": (26.9124, 75.7873)}
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = datetime.datetime.now(IST)

def weather(city, lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&current=temperature_2m&daily=temperature_2m_max,temperature_2m_min,"
           "precipitation_probability_max&timezone=Asia%2FKolkata&forecast_days=7")
    d = json.load(urllib.request.urlopen(url, timeout=30))
    D = d["daily"]; days = []
    for i, t in enumerate(D["time"]):
        day = datetime.date.fromisoformat(t).strftime("%a")
        days.append([day, round(D["temperature_2m_max"][i]), round(D["temperature_2m_min"][i]),
                     f'{D["precipitation_probability_max"][i] or 0}%'])
    rain = max(int(x[3][:-1]) for x in days[:3])
    tip = ("Rain is likely in the next 3 days, carry an umbrella." if rain >= 50
           else "Mostly dry for the next 3 days.")
    return {"city": city, "now": f'Now {round(d["current"]["temperature_2m"])}°C',
            "hi": days[0][1], "lo": days[0][2], "tip": tip, "days": days}

history = json.load(open("jargon_history.json")) if os.path.exists("jargon_history.json") else []

prompt = f"""Today is {today:%A, %d %B %Y} in India. Use web search to find today's top stories
from reputable outlets (e.g. Mint, Times of India, Hindustan Times, The Hindu, BBC, Reuters).
Write ORIGINAL summaries in simple, plain English for a general reader. Never copy sentences
from articles. Return ONLY valid JSON, no markdown, with this exact shape:
{{"world":[{{"h":"headline","s":"2 sentence summary","w":"1-2 sentences explaining it simply and why it matters"}}],
"india":[...], "business":[...], "sports":[...],
"case":{{"h":"catchy question-style title","situation":"2 sentences: the new business situation","story":"3-4 sentences: what happened and why, told like a friendly story","lesson":"1-2 sentences: the takeaway"}},
"astro":[["Aries","one short line"], ... all 12 signs in order],
"jargon":{{"term":"","means":"","formula":"","example":"","why":""}}}}
Give 3 stories each for world, india, business, sports. Business should cover Sensex/Nifty, rupee, and
notable company or economy news. For "jargon" teach ONE basic marketing concept with a simple example
in rupees. Do not use any of these already-used terms: {history}. "case" is a Finshots-style case study: pick ONE fresh business or economy situation from today's news and explain it conversationally, with a simple analogy, no jargon. Astro lines are light, positive, generic."""

client = anthropic.Anthropic()
resp = client.messages.create(
    model=MODEL, max_tokens=6000,
    tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
    messages=[{"role": "user", "content": prompt}])
text = "".join(b.text for b in resp.content if b.type == "text")
data = json.loads(text[text.index("{"): text.rindex("}") + 1])

data["date"] = f"{today:%A, %d %B %Y}"
data["note"] = "Updated automatically every morning. Summaries are AI-written from public news sources."
data["weather"] = [weather(c, *xy) for c, xy in CITIES.items()]

html = open("index.html", encoding="utf-8").read()
block = "const EDITION = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n/* ====="
html = re.sub(r"const EDITION = .*?;\n/\* =====", lambda m: block, html, count=1, flags=re.S)
open("index.html", "w", encoding="utf-8").write(html)

history.append(data["jargon"]["term"])
json.dump(history[-365:], open("jargon_history.json", "w"), indent=1)
print("Edition built for", data["date"])
