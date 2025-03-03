import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any

# Путь к файлам базы данных
RAFFLES_FILE = 'data/raffles.json'
PARTICIPANTS_FILE = 'data/participants.json'

# Создание директории для данных, если она не существует
os.makedirs('data', exist_ok=True)

# Структура базы данных для розыгрышей
# {
#     "raffle_id": {
#         "message_id": 123,
#         "text": "Текст поста",
#         "created_at": "2023-09-01T12:00:00",
#         "end_date": "2023-09-10T12:00:00",
#         "is_active": true,
#         "winners_count": 1,
#         "winners": [null] или [123, 456] (ID победителей)
#     }
# }

# Структура базы данных для участников
# {
#     "raffle_id": {
#         "user_id": {
#             "username": "username",
#             "first_name": "First",
#             "last_name": "Last",
#             "joined_at": "2023-09-01T12:30:00"
#         }
#     }
# }

def _load_json(file_path: str) -> Dict:
    """Загружает данные из JSON файла."""
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump({}, f)
        return {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def _save_json(file_path: str, data: Dict) -> None:
    """Сохраняет данные в JSON файл."""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def create_raffle(message_id: int, text: str, end_date: str, winners_count: int = 1) -> str:
    """Создает новый розыгрыш и возвращает его ID."""
    raffles = _load_json(RAFFLES_FILE)
    
    raffle_id = str(message_id)
    raffles[raffle_id] = {
        "message_id": message_id,
        "text": text,
        "created_at": datetime.now().isoformat(),
        "end_date": end_date,
        "is_active": True,
        "winners_count": winners_count,
        "winners": [None] * winners_count  # Список с None для каждого победителя
    }
    
    _save_json(RAFFLES_FILE, raffles)
    
    # Создаем пустой список участников для этого розыгрыша
    participants = _load_json(PARTICIPANTS_FILE)
    participants[raffle_id] = {}
    _save_json(PARTICIPANTS_FILE, participants)
    
    return raffle_id

def add_participant(raffle_id: str, user_id: int, username: str, first_name: str, last_name: str) -> bool:
    """Добавляет участника в розыгрыш. Возвращает True если участник добавлен, False если уже существует."""
    participants = _load_json(PARTICIPANTS_FILE)
    
    if raffle_id not in participants:
        participants[raffle_id] = {}
    
    user_id_str = str(user_id)
    
    # Если пользователь уже участвует, не добавляем его снова
    if user_id_str in participants[raffle_id]:
        return False
    
    participants[raffle_id][user_id_str] = {
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "joined_at": datetime.now().isoformat()
    }
    
    _save_json(PARTICIPANTS_FILE, participants)
    return True

def get_participants(raffle_id: str) -> List[Dict[str, Any]]:
    """Возвращает список участников розыгрыша."""
    participants = _load_json(PARTICIPANTS_FILE)
    
    if raffle_id not in participants:
        return []
    
    result = []
    for user_id, user_data in participants[raffle_id].items():
        user_info = user_data.copy()
        user_info['user_id'] = int(user_id)
        result.append(user_info)
    
    return result

def get_active_raffles() -> List[Dict[str, Any]]:
    """Возвращает список активных розыгрышей."""
    raffles = _load_json(RAFFLES_FILE)
    
    active_raffles = []
    for raffle_id, raffle_data in raffles.items():
        if raffle_data.get('is_active', False):
            raffle_info = raffle_data.copy()
            raffle_info['raffle_id'] = raffle_id
            active_raffles.append(raffle_info)
    
    return active_raffles

def set_winners(raffle_id: str, winner_ids: List[int]) -> bool:
    """Устанавливает победителей розыгрыша и закрывает его."""
    raffles = _load_json(RAFFLES_FILE)
    
    if raffle_id not in raffles:
        return False
    
    raffles[raffle_id]['winners'] = winner_ids
    raffles[raffle_id]['is_active'] = False
    
    _save_json(RAFFLES_FILE, raffles)
    return True

def get_raffle(raffle_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает информацию о розыгрыше."""
    raffles = _load_json(RAFFLES_FILE)
    
    if raffle_id not in raffles:
        return None
    
    raffle_info = raffles[raffle_id].copy()
    raffle_info['raffle_id'] = raffle_id
    return raffle_info

def is_participant(raffle_id: str, user_id: int) -> bool:
    """Проверяет, участвует ли пользователь в розыгрыше."""
    participants = _load_json(PARTICIPANTS_FILE)
    
    if raffle_id not in participants:
        return False
    
    return str(user_id) in participants[raffle_id]

# Обратная совместимость со старым методом
def set_winner(raffle_id: str, winner_id: int) -> bool:
    """Устаревший метод для совместимости. Устанавливает одного победителя."""
    return set_winners(raffle_id, [winner_id]) 