import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai.errors import APIError

NOTEBOOK_FILE = "Starcraft_notebook.json"

# Стилистика для видеогенерации по Starcraft
STARCRAFT_SYSTEM_PROMPT = (
    "Starcraft cinematic aesthetic, organic alien swarm, zerg hive, "
    "dark sci-fi, cinematic lighting, photorealistic, 8k resolution, ultra detailed."
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
        print(f"[!] Лимит активен. Запросы приостановлены еще на ~{rem_min} мин (до {blocked_until_str}). Выход.")
        return True

    print("[✓] Период ограничения завершился. Возобновляем генерацию видео для Starcraft!")
    data["blocked_until"] = None
    save_notebook(data)
    return False

def find_next_pending_scene(notebook):
    """Ищет первую необработанную сцену среди всех эпизодов."""
    for episode in notebook.get("episodes", []):
        for scene_idx, scene in enumerate(episode.get("scenes", [])):
            if scene.get("status") != "done":
                return episode, scene_idx, scene
    return None, None, None

def run():
    notebook = load_notebook()

    # 1. Проверка кулдауна / лимитов
    if check_cooldown(notebook):
        return

    # 2. Поиск следующей сцены
    episode, scene_idx, scene = find_next_pending_scene(notebook)
    if not scene:
        print("[i] Все сцены во всех сериях Starcraft уже успешно созданы!")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[X] Ошибка: GEMINI_API_KEY не найден в секретах GitHub")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Очищаем текст описания сцены от переносов строк для передачи в промпт
    scene_text = scene.get("description", "").replace("\n", " ").strip()
    full_prompt = (
        f"{STARCRAFT_SYSTEM_PROMPT}, Arc: {episode.get('arc')}, "
        f"Episode: {episode.get('title')}, Scene: {scene_text}"
    )

    ep_num = episode.get("episode_number")
    print(f"\n=== [Starcraft Pipeline] Генерация: Эпизод #{ep_num} | Сцена #{scene_idx + 1} ({scene.get('timecode')}) ===")
    print(f"Промпт: {full_prompt}")

    try:
        operation = client.models.generate_videos(
            model="veo-3.1-generate-001",
            prompt=full_prompt,
            config={
                "aspect_ratio": "16:9",
                "duration_seconds": 5,
            },
        )

        while not operation.done:
            print("  ...генерация сцены продолжается, ожидание 15 секунд...")
            time.sleep(15)
            operation = client.operations.get(operation)

        # Сохранение ссылки на готовое видео
        video_entry = operation.result.generated_videos[0]
        scene["status"] = "done"
        scene["result_url"] = getattr(video_entry.video, "uri", "created_successfully")
        save_notebook(notebook)
        print(f"[✓] Сцена #{scene_idx + 1} серии #{ep_num} успешно создана! Ссылка: {scene['result_url']}")

    except APIError as e:
        err = str(e).upper()
        if e.code == 429 or "RESOURCE_EXHAUSTED" in err:
            now = datetime.now(timezone.utc)
            if "QUOTA" in err or "DAILY" in err:
                cooldown_time = now + timedelta(hours=12)
                print(f"[!] Суточная квота исчерпана. Пауза до: {cooldown_time.isoformat()}")
            else:
                cooldown_time = now + timedelta(minutes=20)
                print(f"[!] Лимит 429. Ожидание 20 минут до: {cooldown_time.isoformat()}")

            notebook["blocked_until"] = cooldown_time.isoformat()
            save_notebook(notebook)
        else:
            print(f"[X] Ошибка запроса: {e}")
            scene["status"] = "failed"
            save_notebook(notebook)
            raise e

if __name__ == "__main__":
    run()
