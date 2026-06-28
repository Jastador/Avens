import requests
import json
import re
from ddgs import DDGS
from config import OLLAMA_MODEL

def research_and_summarize(query):
    print(f"🌍 Avens is browsing the web for: {query}...")
    try:
        # 1. Scrape DuckDuckGo using the new library
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "Sir, I searched the web but could not find any relevant information."
            
        scraped_data = ""
        for i, res in enumerate(results):
            scraped_data += f"Source {i+1}: {res['body']}\n"
            
        # 2. Silent hidden prompt (Doesn't corrupt main memory)
        hidden_prompt = f"Read this live web data I scraped:\n{scraped_data}\nUsing ONLY the data above, answer the user's query: '{query}'. Do not use any tags. Keep it brief."
        print("🧠 Reading the articles and summarizing...")
        
        # 3. Direct, silent request to Ollama
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": hidden_prompt,
            "system": "You are a raw data extractor. Do not roleplay. Do not use tags like < >. Extract the exact price or fact and output ONLY the factual answer.",
            "stream": False,
            "options": {"temperature": 0.3}
        }
        response = requests.post(url, json=payload, timeout=120)
        if response.status_code == 200:
            data = response.json()
            reply = data.get("response", "I read the data, but failed to summarize it.").strip()
            # 🔥 Stop the summarizer brain from echoing tags!
            reply = re.sub(r'<.*?>', '', reply).strip()
            # Kill the template bleed
            if "Below is an instruction" in reply:
                reply = reply.split("Below is an instruction")[0].strip()
            return reply
        return "Sir, my reading module encountered an error."
    except Exception as e:
        print(f"⚠️ Research Error: {e}")
        return "Sir, my connection to the search network was interrupted."