import requests
import logging
import re
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
    
    def get_channel_posts(self, channel: str, target_date: datetime) -> List[Dict]:
        """Парсинг постов канала за целевую дату (позавчера)"""
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
        
        # Диапазон: позавчера (48-24 часа назад)
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        
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
                
                # Проверяем, что пост за позавчера
                if not (day_before.date() <= post_date.date() <= yesterday.date()):
                    continue
                
                # Текст превью
                text_div = msg_div.find('div', class_='tgme_widget_message_text')
                text = text_div.get_text(strip=True) if text_div else ""
                preview = text[:150] + "..." if len(text) > 150 else text
                
                # Просмотры
                views = 0
                views_span = msg_div.find('span', class_='tgme_widget_message_views')
                if views_span:
                    views_text = views_span.get_text(strip=True).replace('K', '000').replace('M', '000000').replace('.', '')
                    match = re.search(r'\d+', views_text)
                    if match:
                        views = int(match.group())
                
                posts.append({
                    'channel_id': 0,
                    'message_id': msg_id,
                    'channel': channel,
                    'channel_title': channel,
                    'reactions': 0,
                    'views': views,
                    'text': preview,
                    'date': post_date
                })
                
            except Exception as e:
                logger.warning(f"Ошибка парсинга поста в {channel}: {e}")
                continue
        
        logger.info(f"Канал {channel}: за период найдено {len(posts)} постов")
        return posts
    
    def get_best_post(self, channel: str, target_date: datetime) -> Optional[Dict]:
        """Лучший пост за дату (по просмотрам, т.к. реакций нет в HTML)"""
        posts = self.get_channel_posts(channel, target_date)
        if not posts:
            return None
        
        posts.sort(key=lambda x: x['views'], reverse=True)
        return posts[0]