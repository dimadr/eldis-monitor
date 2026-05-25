import requests
from typing import Any, Optional
from datetime import datetime as dt

from app.config import settings


class AuthenticationError(Exception):
    """Ошибка авторизации в API ЭЛДИС"""
    pass


class APIError(Exception):
    """Ошибка API ЭЛДИС"""
    pass


class Client:
    """Клиент для работы с API ЭЛДИС"""
    
    def __init__(self, base_url: str, login: str, password: str, api_key: str, mock: bool = False):
        self.base_url = base_url
        self.login = login
        self.password = password
        self.api_key = api_key
        self._token: Optional[str] = None
        self._mock = mock

    def _login(self) -> bool:
        """Авторизация в API ЭЛДИС
        
        Endpoint: POST /api/v2/users/login
        Поля: username, password
        Заголовок: key (API key)
        Content-Type: application/x-www-form-urlencoded
        
        Returns:
            True если авторизация успешна
            
        Raises:
            AuthenticationError: если авторизация не удалась
        """
        url = f"{self.base_url}/api/v2/users/login"
        data = {
            "login": self.login,
            "password": self.password,
        }
        headers = {
            "key": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise AuthenticationError(f"Ошибка соединения с API: {e}")
        
        try:
            resp_data = response.json()
        except ValueError:
            raise AuthenticationError("Некорректный ответ от API (не JSON)")
        
        # Проверяем статус в ответе API
        messages = resp_data.get("response", {}).get("messages", [])
        if not messages:
            raise AuthenticationError("Пустой ответ от API")
        
        msg = messages[0]
        http_status = msg.get("httpStatusCode")
        message_text = msg.get("message", "Неизвестная ошибка")
        
        if http_status == 200:
            # Успешная авторизация
            access_token = response.cookies.get("access_token")
            if access_token:
                self._token = access_token
                return True
            else:
                # Попробуем получить из Set-Cookie заголовка
                set_cookie = response.headers.get('Set-Cookie', '')
                import re
                match = re.search(r'access_token=([^;]+)', set_cookie)
                if match:
                    self._token = match.group(1)
                    return True
                raise AuthenticationError("Авторизация успешна, но access_token не получен")
        elif http_status == 400:
            raise AuthenticationError(
                f"Пользователь не найден. "
                f"Проверьте логин ({self.login})"
            )
        elif http_status == 401:
            raise AuthenticationError(
                f"Неверный пароль или учетная запись не активирована для API. "
                f"Проверьте: 1) Правильность пароля 2) Активацию API доступа в личном кабинете"
            )
        elif http_status == 403:
            raise AuthenticationError(
                f"Неверный API ключ или ключ не активирован. "
                f"Проверьте ключ API в личном кабинете ЭЛДИС"
            )
        else:
            raise AuthenticationError(f"Ошибка авторизации: {message_text} (код {http_status})")

    def _ensure_auth(self):
        """Проверяет авторизацию, при необходимости выполняет login"""
        if self._mock:
            return
        if not self._token:
            if not self._login():
                raise AuthenticationError("Не удалось авторизоваться в API ЭЛДИС")

    def get(self, path: str, **kwargs) -> Any:
        """Выполняет GET запрос к API
        
        Args:
            path: путь к endpoint'у
            **kwargs: дополнительные параметры requests
            
        Returns:
            JSON ответ от API
            
        Raises:
            AuthenticationError: если не удалось авторизоваться
            APIError: если API вернуло ошибку
        """
        self._ensure_auth()
        if not self._mock and not self._token:
            raise AuthenticationError("Не авторизован")
            
        url = f"{self.base_url}{path}"
        # Заголовки согласно документации ELDIS API:
        # key: API ключ
        # Cookie: access_token (передается через cookies)
        headers = {"key": self.api_key}
        cookies: dict[str, str] = {"access_token": self._token}
        
        try:
            response = requests.get(
                url, 
                headers=headers, 
                cookies=cookies, 
                timeout=30,
                **kwargs
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise APIError(f"Ошибка запроса к API: {e}")
        
        try:
            data = response.json()
        except ValueError:
            raise APIError("Некорректный ответ от API (не JSON)")
        
        # Проверяем статус ответа API
        messages = data.get("response", {}).get("messages", [])
        if messages:
            msg = messages[0]
            http_status = msg.get("httpStatusCode", 200)
            if http_status != 200:
                message_text = msg.get("message", "Неизвестная ошибка")
                if http_status == 401:
                    # Сессия истекла, пробуем перелогиниться
                    self._token = None
                    self._ensure_auth()
                    # Повторяем запрос
                    return self.get(path, **kwargs)
                raise APIError(f"Ошибка API: {message_text} (код {http_status})")
        
        return data

    def get_devices(self) -> Any:
        """Получить список точек учета (приборов)
        
        Returns:
            Список точек учета или пустой список если приборов нет
        """
        if self._mock:
            return {
                "response": {
                    "tv": {
                        "listForDevelopment": {
                            "1": {"id": 1, "name": "Теплосчетчик №1", "type": "heat"},
                            "2": {"id": 2, "name": "Водосчетчик ХВС", "type": "water"},
                        }
                    },
                    "messages": [{"httpStatusCode": 200, "message": "OK"}]
                }
            }
        return self.get("/api/v2/tv/listForDevelopment")

    def get_user_info(self, user_id: Optional[str] = None) -> Any:
        """Получить информацию о пользователе
        
        Args:
            user_id: ID пользователя (если None - информация о текущем пользователе)
            
        Returns:
            Информация о пользователе
            
        Endpoint: GET /api/v2/users/get
        """
        params = {}
        if user_id:
            params["id"] = user_id
        return self.get("/api/v2/users/get", params=params)

    def get_normalized_readings(
        self,
        device_id: str,
        archive_type: int = 4,
        start_date: Optional[dt] = None,
        end_date: Optional[dt] = None,
    ) -> Any:
        """Получить нормализованные показания прибора

        Args:
            device_id: ID точки учета
            archive_type: тип архива (по умолчанию 4 - часовой)
            start_date: начальная дата
            end_date: конечная дата

        Returns:
            Данные показаний
        """
        if self._mock:
            import random
            return {
                "response": {
                    "data": {
                        "normalized": {
                            device_id: [
                                {
                                    "timestamp": "2026-03-10T10:00:00",
                                    "value": random.uniform(1000, 2000),
                                    "status": "ok"
                                }
                            ]
                        }
                    },
                    "messages": [{"httpStatusCode": 200, "message": "OK"}]
                }
            }
        params = {
            "id": device_id,
            "typeDataCode": archive_type,
        }
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        return self.get("/api/v2/data/normalized", params=params)

    def logout(self) -> None:
        """Выход из API (завершение сессии)"""
        if self._token:
            try:
                url = f"{self.base_url}/api/v2/users/logout"
                headers = {"key": self.api_key}
                cookies = {"access_token": self._token}
                requests.get(url, headers=headers, cookies=cookies, timeout=10)
            except Exception:
                pass
            finally:
                self._token = None


def get_client(mock: bool = False) -> Client:
    """Создает и возвращает настроенный клиент API
    
    Args:
        mock: если True, использовать mock-данные вместо реального API.
               По умолчанию используется значение из settings.MOCK_MODE
    """
    # Если mock не передан явно, используем настройку из конфига
    effective_mock = mock if mock else settings.MOCK_MODE
    
    return Client(
        base_url=settings.ELDIS_API_URL,
        login=settings.ELDIS_LOGIN,
        password=settings.ELDIS_PASSWORD,
        api_key=settings.ELDIS_API_KEY,
        mock=effective_mock,
    )


def test_connection() -> dict:
    """Тестирует подключение к API и возвращает результаты
    
    Returns:
        Словарь с результатами проверки
    """
    results = {
        "success": False,
        "login": settings.ELDIS_LOGIN,
        "api_url": settings.ELDIS_API_URL,
        "error": None,
        "devices_count": 0,
    }
    
    try:
        client = get_client()
        client._login()
        results["success"] = True
        results["message"] = "Авторизация успешна"
        
        # Пробуем получить устройства
        try:
            devices_data = client.get_devices()
            tv_data = devices_data.get("response", {}).get("tv", {}).get("listForDevelopment", {})
            results["devices_count"] = len(tv_data) if isinstance(tv_data, dict) else 0
            results["message"] += f", найдено {results['devices_count']} устройств"
        except Exception as e:
            results["message"] += f", но не удалось получить список устройств: {e}"
            
    except AuthenticationError as e:
        results["error"] = str(e)
    except Exception as e:
        results["error"] = f"Неожиданная ошибка: {e}"
    
    return results


if __name__ == "__main__":
    # Тест при запуске файла напрямую
    print("=== Тест подключения к ELDIS API ===\n")
    results = test_connection()
    
    for key, value in results.items():
        print(f"{key}: {value}")
