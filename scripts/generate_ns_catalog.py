#!/usr/bin/env python3
"""
Генератор справочника нештатных ситуаций для ИИ-модели
Создает оптимизированный JSON для быстрого анализа
"""

import requests
import json
from pathlib import Path

OUTPUT_DIR = Path("/root/eldis/eldis-monitor")
CATALOG_FILE = OUTPUT_DIR / "ns_catalog.json"

def get_api_data():
    """Получение данных через API"""
    import os
    api_key = os.environ.get('ELDIS_API_KEY', '')
    login = os.environ.get('ELDIS_LOGIN', '')
    password = os.environ.get('ELDIS_PASSWORD', '')

    session = requests.Session()
    headers = {
        'key': api_key,
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    login_data = {'login': login, 'password': password}
    resp = session.post('https://api.eldis24.ru/api/v1/users/login', data=login_data, headers=headers)
    token = session.cookies.get('access_token')
    headers['Cookie'] = f'access_token={token}'

    return session, headers

def get_device_models(session, headers):
    """Получение списка моделей приборов"""
    models = []
    for page in range(1, 10):
        data = {'limit': 50, 'page': page}
        resp = session.post('https://api.eldis24.ru/api/v1/search/deviceModels', data=data, headers=headers)
        result = resp.json()
        items = result.get('response', {}).get('search', {}).get('deviceModels', [])
        models.extend(items)
        if len(items) < 50:
            break
    return models

def get_ns_events(session, headers):
    """Получение событий нештатных ситуаций"""
    # Основные группы SN
    sn_groups = {
        4244: "SN00",
        4240: "SN01", 
        4235: "SN02",
        4236: "SN03",
        4252: "SN04",
        4242: "SN05",
        4247: "SN99"
    }
    
    # Другие группы НС
    other_groups = {
        3202: "НС МКТС ТС",
        3203: "Неполное время работы ТС",
        3204: "Неполное время работы ГВС",
        3206: "Неполное время работы Газ",
        3207: "НС МКТС ГВС",
        3218: "Нет архивов",
        3258: "Небаланс масс"
    }
    
    all_groups = {**sn_groups, **other_groups}
    events = {}
    
    for group_id, group_name in all_groups.items():
        data = {'limit': 100, 'groupEventID': group_id}
        resp = session.post('https://api.eldis24.ru/api/v1/search/events', data=data, headers=headers)
        result = resp.json()
        items = result.get('response', {}).get('search', {}).get('events', [])
        events[group_id] = {
            "name": group_name,
            "events": [
                {
                    "code": e.get("code"),
                    "name": e.get("name")
                }
                for e in items
            ]
        }
    
    return events

def get_resource_types(session, headers):
    """Получение типов ресурсов"""
    return {
        1: "Тепловая энергия",
        2: "Горячая вода",
        4: "Холодная вода",
        5: "Газ",
        6: "Электричество",
        10: "Сточные воды",
        11: "Пар"
    }

def analyze_ns_mapping():
    """
    Анализ соответствия полей данных NS кодам событий
    Это нужно для справочника - какое поле = какой код НС
    """
    return {
        "TGmax": {
            "description": "Время выше максимального расхода",
            "ns_group": "SN02",
            "events": [
                "Выход G из рабочего режима",
                "Превышение максимального расхода"
            ]
        },
        "TGmin": {
            "description": "Время ниже минимального расхода", 
            "ns_group": "SN03",
            "events": [
                "Выход G из рабочего режима",
                "Значение величины V ниже значения уставки"
            ]
        },
        "TFault": {
            "description": "Время функционального отказа",
            "ns_group": "SN04",
            "events": [
                "Функциональный отказ",
                "Неисправность датчика"
            ]
        },
        "Toff": {
            "description": "Время отключения питания",
            "ns_group": "SN01",
            "events": [
                "Отключение питания",
                "Потеря связи"
            ]
        },
        "TOtherNS": {
            "description": "Время других нештатных ситуаций",
            "ns_group": "SN99",
            "events": [
                "Прочие нештатные ситуации"
            ]
        },
        "QntHIP": {
            "description": "Время нормальной работы",
            "ns_group": "SN00",
            "events": [
                "Время наработки больше допустимого",
                "Нормальная работа"
            ]
        },
        "QntP": {
            "description": "Время отсутствия счёта",
            "ns_group": "SN05",
            "events": [
                "Отсутствие счёта",
                "Нет данных"
            ]
        }
    }

def create_catalog():
    """Создание полного каталога"""
    print("Подключение к API...")
    session, headers = get_api_data()
    
    print("Получение моделей приборов...")
    device_models = get_device_models(session, headers)
    print(f"  Найдено моделей: {len(device_models)}")
    
    print("Получение событий НС...")
    ns_events = get_ns_events(session, headers)
    print(f"  Найдено групп НС: {len(ns_events)}")
    
    print("Создание каталога...")
    
    # Создаем структуру каталога
    catalog = {
        "version": "1.0",
        "created": "2026-03-12",
        "description": "Справочник нештатных ситуаций для ИИ-анализа",
        
        # Справочник моделей приборов
        "device_models": {
            m["code"]: {
                "name": m["name"],
                "id": m["id"]
            }
            for m in device_models
        },
        
        # Справочник типов ресурсов
        "resource_types": get_resource_types(session, headers),
        
        # Справочник НС - основной раздел
        "ns_events": ns_events,
        
        # Карта соответствия полей данных кодам НС
        "data_field_to_ns": analyze_ns_mapping(),
        
        # Упрощенный справочник для быстрого поиска
        "ns_quick_ref": {
            # Код события -> (группа, описание, поле в данных)
            317: {"group": "SN00", "desc": "Qфакт.сут < Qдог.сут", "field": None},
            316: {"group": "SN00", "desc": "Qфакт.сут > Qдог.сут", "field": None},
            278: {"group": "SN00", "desc": "Q факт.сут < Qэфф.сут", "field": None},
            277: {"group": "SN00", "desc": "Q факт.сут > Qэфф.сут", "field": None},
            276: {"group": "SN00", "desc": "Q факт.час < Qэфф.час", "field": None},
            275: {"group": "SN00", "desc": "Q факт.час > Qэфф.час", "field": None},
            282: {"group": "SN00", "desc": "Авария! Высокая температура подачи!", "field": "t1"},
            283: {"group": "SN00", "desc": "Авария! Низкая температура обратки!", "field": "t2"},
            314: {"group": "SN00", "desc": "Время наработки больше допустимого", "field": "QntHIP"},
            352: {"group": "SN01", "desc": "Выход Ap из рабочего режима", "field": None},
            180: {"group": "SN02", "desc": "Выход dMгвс из рабочего режима потребления", "field": "TGmin/TGmax"},
            325: {"group": "SN02", "desc": "Выход dMтс из рабочего режима потребления", "field": "TGmin/TGmax"},
            176: {"group": "SN03", "desc": "Выход dMтс из рабочего режима потребления", "field": "TGmin"},
            207: {"group": "SN03", "desc": "Выход dPгвс из рабочего режима потребления", "field": "TGmin/TGmax"},
            203: {"group": "SN03", "desc": "Выход dPтс из рабочего режима потребления", "field": "TGmin/TGmax"},
            198: {"group": "SN03", "desc": "Выход dtгвс из рабочего режима потребления", "field": "TGmin"},
            329: {"group": "SN04", "desc": "Выход dtтс из рабочего режима потребления", "field": "TGmin"},
            194: {"group": "SN04", "desc": "Выход dtтс из рабочего режима", "field": "TGmax"},
        }
    }
    
    # Сохраняем
    with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    
    print(f"\nКаталог сохранен: {CATALOG_FILE}")
    print(f"Размер: {CATALOG_FILE.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    create_catalog()
