import json
import os
import sys
import time
from google import genai
from google.genai.errors import APIError

QUEUE_FILE = "tasks.json"

def load_tasks():
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tasks(tasks):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

def run():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Помилка: Не знайдено GEMINI_API_KEY")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    tasks = load_tasks()

    task = next((t for t in tasks if t["status"] == "pending"), None)
    if not task:
        print("Всі задачі виконано!")
        return

    print(f"Обробка задачі #{task['id']}: {task['prompt']}")
    try:
        # Використовуємо актуальну модель Veo
        operation = client.models.generate_videos(
            model="veo-3.1-generate-001",
            prompt=task["prompt"],
            config={
                "aspect_ratio": "16:9",
                "duration_seconds": 5,
            },
        )
        
        while not operation.done:
            print("Генерація триває (очікування 15 сек)...")
            time.sleep(15)
            operation = client.operations.get(operation)

        # Отримання посилання на результат
        result_video = operation.result.generated_videos[0]
        task["status"] = "done"
        task["result_url"] = getattr(result_video.video, "uri", "generated_successfully")
        save_tasks(tasks)
        print(f"Успішно! Результат: {task['result_url']}")

    except APIError as e:
        if e.code == 429 or "RESOURCE_EXHAUSTED" in str(e):
            print("Ліміт вичерпано. Задача залишається pending до наступного запуску.")
        else:
            print(f"Помилка API: {e}")
            task["status"] = "failed"
            save_tasks(tasks)
            raise e

if __name__ == "__main__":
    run()
