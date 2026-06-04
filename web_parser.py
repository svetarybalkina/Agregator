import requests
import logging
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebParser:
    def __init__(self, proxy=None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        if proxy:
            self.session.proxies = {'http': proxy, 'https': proxy}
    
    def _get_page(self, url: str) -> Optional[str]:
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка загрузки {url}: {e}")
            return None
    
    def _parse_post_page(self, channel: str, message_id: int) -> Optional[Dict]:
        """Парсинг отдельной страницы поста для получения реакций"""
        url = f"https://t.me/{channel}/{message_id}"
        html = self._get_page(url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Ищем блок сообщения по data-post
        message_div = soup.find('div', {'data-post': f"{channel}/{message_id}"})
        if not message_div:
            # Fallback — ищем любой блок сообщения
            message_div = soup.find('div', class_='tgme_widget_message')
        
        if not message_div:
            logger.warning(f"Не найден блок сообщения для {channel}/{message_id}")
            return None
        
        # Дата
        time_elem = message_div.find('time')
        post_date = None
        if time_elem and time_elem.get('datetime'):
            try:
                post_date = datetime.fromisoformat(time_elem['datetime'].replace('Z', '+00:00'))
                post_date = post_date.replace(tzinfo=None)
            except ValueError:
                pass
        
        # Текст
        text_div = message_div.find('div', class_='tgme_widget_message_text')
        text = text_div.get_text(strip=True) if text_div else ""
        preview = text[:150] + "..." if len(text) > 150 else text
        
        # РЕАКЦИИ — исправленный парсинг
        reactions = 0
        
        # Контейнер реакций
        reactions_container = message_div.find('div', class_='tgme_widget_message_reactions')
        if reactions_container:
            # Каждая реакция внутри <span class="tgme_reaction">
            reaction_spans = reactions_container.find_all('span', class_='tgme_reaction')
            for reaction in reaction_spans:
                # Счётчик внутри <span class="counter_value">
                count_elem = reaction.find('span', class_='counter_value')
                if count_elem:
                    count_text = count_elem.get_text(strip=True)
                    # Обрабатываем K и M
                    count_text = count_text.replace('K', '000').replace('M', '000000').replace('.', '')
                    try:
                        reactions += int(count_text)
                    except ValueError:
                        pass
        
        # Просмотры
        views = 0
        views_span = message_div.find('span', class_='tgme_widget_message_views')
        if views_span:
            views_text = views_span.get_text(strip=True).replace('K', '000').replace('M', '000000').replace('.', '')
            match = re.search(r'\d+', views_text)
            if match:
                views = int(match.group())
        
        result = {
            'channel_id': 0,
            'message_id': message_id,
            'channel': f"@{channel}",
            'channel_title': f"@{channel}",
            'reactions': reactions,
            'views': views,
            'text': preview,
            'date': post_date
        }
        
        logger.info(f"  Пост {message_id}: {reactions} реакций, {views} просмотров")
        return result
    
    def get_channel_posts(self, channel: str, target_date: datetime) -> List[Dict]:
        """Получение постов канала за целевую дату (позавчера)"""
        posts = []
        channel_clean = channel.replace('@', '')
        url = f"https://t.me/s/{channel_clean}"
        
        html = self._get_page(url)
        if not html:
            logger.error(f"Не удалось загрузить канал {channel}")
            return posts
        
        soup = BeautifulSoup(html, 'lxml')
        message_divs = soup.find_all('div', class_='tgme_widget_message')
        
        logger.info(f"Канал {channel}: найдено {len(message_divs)} постов на странице")
        
        # Диапазон: последние 3 дня для надёжности
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        day_before = now - timedelta(days=3)
        
        # Собираем ID постов за нужную дату
        post_ids = []
        for msg_div in message_divs:
            try:
                data_post = msg_div.get('data-post', '')
                if not data_post or '/' not in data_post:
                    continue
                
                msg_id = int(data_post.split('/')[-1])
                
                # Дата поста
                time_elem = msg_div.find('time')
                if not time_elem or not time_elem.get('datetime'):
                    continue
                
                date_str = time_elem['datetime']
                post_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                post_date = post_date.replace(tzinfo=None)
                
                # Проверяем, что пост за последние 3 дня
                if day_before.date() <= post_date.date() <= yesterday.date():
                    post_ids.append(msg_id)
                    
            except Exception as e:
                logger.warning(f"Ошибка парсинга поста в {channel}: {e}")
                continue
        
        logger.info(f"Канал {channel}: за период найдено {len(post_ids)} постов")
        
        # Теперь заходим на каждый пост отдельно для получения реакций
        for msg_id in post_ids:
            post_data = self._parse_post_page(channel_clean, msg_id)
            if post_data:
                posts.append(post_data)
            # Задержка чтобы не забанили
            time.sleep(0.8)
        
        return posts
    
    def get_best_post(self, channel: str, target_date: datetime) -> Optional[Dict]:
        """Лучший пост за дату по реакциям"""
        posts = self.get_channel_posts(channel, target_date)
        if not posts:
            return None
        
        # СОРТИРОВКА ПО РЕАКЦИЯМ (основной критерий), затем по просмотрам
        posts.sort(key=lambda x: (x['reactions'], x['views']), reverse=True)
        return posts[0]