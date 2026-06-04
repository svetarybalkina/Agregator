import requests
from bs4 import BeautifulSoup
import re

# Укажите реальный ID поста из канала @twitt_ota
# Посмотрите на https://t.me/s/twitt_ota и возьмите номер любого поста
POST_ID = 12345  # <-- ЗАМЕНИТЕ НА РЕАЛЬНЫЙ ID

url = f"https://t.me/s/naokraine404/39318"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

print(f"Загружаю: {url}")
response = requests.get(url, headers=headers, timeout=30)
print(f"Статус: {response.status_code}")
print(f"Длина HTML: {len(response.text)}")

soup = BeautifulSoup(response.text, 'lxml')

# Ищем блок сообщения
message_div = soup.find('div', {'data-post': True})
print(f"\nНайден data-post: {message_div.get('data-post') if message_div else 'НЕТ'}")

# Ищем реакции всеми способами
print("\n--- Поиск реакций ---")

# Способ 1
reactions_container = soup.find('div', class_='tgme_widget_message_reactions')
print(f"reactions_container: {reactions_container is not None}")

# Способ 2
all_reactions = soup.find_all('div', class_=re.compile('reaction'))
print(f"all_reactions count: {len(all_reactions)}")

# Способ 3
main_div = soup.find('div', class_='tgme_widget_message')
reaction_data = main_div.get('data-reactions') if main_div else None
print(f"data-reactions: {reaction_data}")

# Способ 4
spans = soup.find_all('span', class_=re.compile('count|counter'))
print(f"spans with count/counter: {len(spans)}")
for s in spans[:5]:
    print(f"  текст: '{s.get_text(strip=True)}' | класс: {s.get('class')}")

# Проверяем, есть ли слово "reaction" в HTML
if 'reaction' in response.text.lower():
    idx = response.text.lower().find('reaction')
    print(f"\nНайдено 'reaction' в HTML на позиции {idx}")
    print(f"Контекст: {response.text[idx-50:idx+150]}")
else:
    print("\nСлово 'reaction' не найдено в HTML")

# Ищем просмотры (views)
views_span = soup.find('span', class_='tgme_widget_message_views')
if views_span:
    print(f"\nПросмотры: {views_span.get_text(strip=True)}")
else:
    print("\nПросмотры: не найдены")

print("\n=== ГОТОВО ===")