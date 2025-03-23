import time
from django.core.cache import cache
import requests
from django.conf import settings

def auth_token(request):
    # Получение кода авторизации из параметров запроса
    code = request.GET.get('code', '')

    # Отправка запроса на получение токена
    response = requests.post(f"{settings.OAUTH_ACCESS_TOKEN_URL}?code={code}")

    # Проверка успешности ответа
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()
        
def get_current_user(request):
    # Получение токена из Redis
    session_key = f"session_{request.session.session_key}"
    token = cache.get(f"{session_key}_token")

    # Если токен отсутствует или не содержит `access_token`, возвращаем None
    if token is None or 'access_token' not in token:
        return None

    # Проверка на истечение срока действия токена
    if not OAuth2Token.from_dict(token).is_expired():
        user = cache.get(f"{session_key}_user")
        if user:
            return user

    # Если токен действителен, делаем запрос на получение данных пользователя
    try:
        res = requests.get(f"{settings.OAUTH_PROFILE_URL}?access_token={token.get('access_token')}")
        if res.ok:
            user_json = res.json()
            print(user_json)
            user = {
                'firstname': user_json.get('firstname', ''),
                'lastname': user_json.get('lastname', ''),
                'middlename': user_json.get('middlename', ''),
                'alias': user_json.get('alias', ''),
                'username': user_json.get('username', '')
            }

            # Сохраняем данные пользователя в Redis
            cache.set(f"{session_key}_user", user, timeout=3600)  # Срок действия - 1 час
            return user
    except Exception as e:
        print(f"Ошибка при получении пользователя: {e}")
    
    return None

def set_user_state(telegram_id, state):
    cache.set(f"state_{telegram_id}", state, timeout=300)  # Храним состояние 5 минут

def get_user_state(telegram_id):
    return cache.get(f"state_{telegram_id}")

def clear_session(request):
    session_key = f"session_{request.session.session_key}"
    # Удаляем данные пользователя и токена из Redis
    cache.delete(f"{session_key}_user")
    cache.delete(f"{session_key}_token")

class OAuth2Token(dict):
    def __init__(self, params):
        # Вычисляем время истечения токена
        if params.get('expires_at'):
            params['expires_at'] = int(params['expires_at'])
        elif params.get('expires_in'):
            params['expires_at'] = int(time.time()) + int(params['expires_in'])
        super(OAuth2Token, self).__init__(params)

    def is_expired(self):
        # Проверяем, истек ли токен
        expires_at = self.get('expires_at')
        if not expires_at:
            return None
        return expires_at < time.time()

    @classmethod
    def from_dict(cls, token):
        # Преобразуем словарь в объект `OAuth2Token`
        if isinstance(token, dict) and not isinstance(token, cls):
            token = cls(token)
        return token
    
    