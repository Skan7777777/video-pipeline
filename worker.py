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
        print("Ошибка: Не найден GEMINI_API_KEY")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    tasks = load_tasks()

    task = next((t for t in tasks if t["status"] == "pending"), None)
    if not task:
        print("Все задачи выполнены!")
        return

    print(f"Обработка задачи #{task['id']}: {task['prompt']}")
    try:
        operation = client.models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=task["prompt"],
            config={"aspect_ratio": "16:9", "duration_seconds": 5},
        )

        while not operation.done:
            print("Генерация продолжается...")
            time.sleep(15)
            operation = client.operations.get(operation)

        task["status"] = "done"
        task["result_url"] = operation.result.generated_videos[0].video.uri
        save_tasks(tasks)
        print(f"Успешно! URI: {task['result_url']}")

    except APIError as e:
        if e.code == 429 or "RESOURCE_EXHAUSTED" in str(e):
            print("Лимит исчерпан. Задача остается pending до следующего запуска.")
        else:
            task["status"] = "failed"
            save_tasks(tasks)
            raise e

if __name__ == "__main__":
    run()
