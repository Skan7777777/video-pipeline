import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai.errors import APIError

NOTEBOOK_FILE = "Starcraft_notebook.json"

# Системне налаштування стилю кожного нового сеансу
WARHAMMER_SYSTEM_PROMPT = (
    "Warhammer 40,000 grimdark aesthetic, highly detailed, gothic sci-fi, "
    "cinematic lighting, photorealistic."
)

def load_notebook():
    with open(NOTEBOOK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_notebook(data):
    with open(NOTEBOOK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def check_cooldown(data):
    blocked_until_str = data.get("blocked_until")
    if not blocked_until_str:
        return False

    blocked_until = datetime.fromisoformat(blocked_until_str)
    now = datetime.now(timezone.utc)

    if now < blocked_until:
        rem_min = int((blocked_until - now).total_seconds() / 60)
        print(f"[!] Ліміт активний. Запити призупинено ще на ~{rem_min} хв (до {blocked_until_str}). Вихід.")
        return True

    print("[✓] Період обмеження минув. Відновлюємо створення відео у блокноті Вархаммер!")
    data["blocked_until"] = None
    save_notebook(data)
    return False

def run():
    notebook = load_notebook()

    # 1. Перевірка обмеження за часом
    if check_cooldown(notebook):
        return

    # 2. Знаходимо наступну задачу в блокноті
    task = next((t for t in notebook["tasks"] if t["status"] == "pending"), None)
    if not task:
        print("[i] Усі сцени у блокноті Вархаммер вже успішно створені!")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[X] Помилка: GEMINI_API_KEY не знайдено в секретах GitHub")
        sys.exit(1)

    # Ініціалізація нового клієнта (чистий сеанс / новий чат)
    client = genai.Client(api_key=api_key)

    full_prompt = f"{WARHAMMER_SYSTEM_PROMPT}, {task['prompt']}"
    print(f"\n=== [Блокнот Вархаммер] Новий чат: Задача #{task['id']} ===")
    print(f"Промпт: {full_prompt}")

    try:
        # Запит на створення відео до моделі
        operation = client.models.generate_videos(
            model="veo-3.1-generate-001",
            prompt=full_prompt,
            config={
                "aspect_ratio": "16:9",
                "duration_seconds": 5,
            },
        )

        while not operation.done:
            print("  ...генерація сцени триває, очікування 15 секунд...")
            time.sleep(15)
            operation = client.operations.get(operation)

        # Фіксація успішного результату
        video_entry = operation.result.generated_videos[0]
        task["status"] = "done"
        task["result_url"] = getattr(video_entry.video, "uri", "created_successfully")
        save_notebook(notebook)
        print(f"[✓] Сцену #{task['id']} успішно створено! Посилання: {task['result_url']}")

    except APIError as e:
        err = str(e).upper()
        if e.code == 429 or "RESOURCE_EXHAUSTED" in err:
            now = datetime.now(timezone.utc)
            # Якщо добовий ліміт — пауза до ранку (12 годин), якщо хвилинний — 20 хвилин
            if "QUOTA" in err or "DAILY" in err:
                cooldown_time = now + timedelta(hours=12)
                print(f"[!] Добову квоту вичерпано. Блокнот спить до: {cooldown_time.isoformat()}")
            else:
                cooldown_time = now + timedelta(minutes=20)
                print(f"[!] Ліміт 429. Очікування 20 хвилин до: {cooldown_time.isoformat()}")

            notebook["blocked_until"] = cooldown_time.isoformat()
            save_notebook(notebook)
        else:
            print(f"[X] Помилка запиту: {e}")
            task["status"] = "failed"
            save_notebook(notebook)
            raise e

if __name__ == "__main__":
    run()
