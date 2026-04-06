import telebot
import openai
import requests
import json
import yt_dlp
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def keep_alive():
    """Starts a basic HTTP server to keep the service running."""
    port = int(os.environ.get('PORT', 8080))
    HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler).serve_forever()

threading.Thread(target=keep_alive, daemon=True).start()

# Environment Variables & Initialization
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
INSTACART_API_KEY = os.getenv("INSTACART_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = openai.OpenAI(api_key=OPENAI_API_KEY)

def get_video_transcript(url):
    """Downloads audio from a given URL and transcribes it using Whisper."""
    print(f"[Info] Downloading audio from: {url}")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'recipe_audio.%(ext)s',
        'quiet': True
    }
    
    audio_filename = "recipe_audio.m4a"
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        
    print("[Info] Transcribing audio...")
    with open(audio_filename, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file
        )
        
    if os.path.exists(audio_filename):
        os.remove(audio_filename)
        
    return transcript.text

def extract_ingredients_json(recipe_text):
    """Extracts ingredients from text and formats them as a structured JSON object."""
    system_prompt = """
    You are a culinary AI. The user will give you a recipe transcript. 
    Extract the ingredients and return a strict JSON object that exactly matches this structure:
    {
      "title": "Name of Recipe",
      "ingredients": [
        {
          "name": "Ingredient Name (e.g. onion)",
          "measurements": [
            {
              "quantity": 1,
              "unit": "each"
            }
          ]
        }
      ]
    }
    """
    
    print("[Info] Extracting ingredients to JSON...")
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": recipe_text}
        ]
    )
    
    return json.loads(response.choices[0].message.content)

def generate_shoppable_url(recipe_data):
    """Sends recipe JSON to Instacart API to generate a shoppable cart link."""
    print("[Info] Building shoppable link...")
    url = "https://connect.instacart.com/idp/v1/products/recipe"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {INSTACART_API_KEY}"
    }
    
    response = requests.post(url, headers=headers, json=recipe_data)
    
    if response.status_code == 200:
        return response.json().get("products_link_url")
    else:
        return "https://www.instacart.com/store (PENDING REAL API KEY)"

@bot.message_handler(func=lambda message: True)
def handle_recipe_request(message):
    """Main message handler for processing incoming recipe links."""
    if "http" not in message.text:
        bot.reply_to(message, "❌ Please send a valid link.")
        return
        
    bot.reply_to(message, "🍳 Processing recipe... extracting ingredients and building cart.")
    
    try:
        spoken_recipe_text = get_video_transcript(message.text)
        recipe_json = extract_ingredients_json(spoken_recipe_text)
        magic_link = generate_shoppable_url(recipe_json)
        
        bot.reply_to(message, f"🔥 Recipe processed: {recipe_json['title']}\n\n🛒 Shoppable link:\n{magic_link}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error processing request: {e}")

if __name__ == "__main__":
    print("[System] Bot is online and polling...")
    bot.polling()