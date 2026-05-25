#!/usr/bin/env python3
"""
Пример использования справочника НС для ИИ-анализа
"""

import json
from pathlib import Path

# Загрузка справочника
DICT_PATH = Path(__file__).parent.parent / "ns_dictionary.json"

with open(DICT_PATH, 'r', encoding='utf-8') as f:
    NS_DICT = json.load(f)

def analyze_ns(data_record: dict) -> dict:
    """
    Анализ записи данных на основе справочника НС
    
    Args:
        data_record: dict с полями TGmin, TGmax, TFault, Toff, QntHIP, QntP, ns
        
    Returns:
        dict с интерпретацией НС
    """
    result = {
        "has_ns": data_record.get("ns", False),
        "detected_issues": [],
        "summary": []
    }
    
    if not result["has_ns"]:
        return result
    
    # Проверяем каждое поле
    for field, value in data_record.items():
        if field in NS_DICT["field_to_ns"] and value and value > 0:
            field_info = NS_DICT["field_to_ns"][field]
            result["detected_issues"].append({
                "field": field,
                "description": field_info["description"],
                "value_hours": value,
                "possible_ns": field_info["ns_names"]
            })
            result["summary"].append(
                f"{field}={value}ч: {field_info['ns_names'][0]}"
            )
    
    return result

def get_ns_description(code: int) -> str:
    """Получить описание НС по коду"""
    return NS_DICT["ns_by_code"].get(str(code), "Неизвестный код")

# Пример использования
if __name__ == "__main__":
    # Тестовые данные (как в вашем отчёте)
    test_record = {
        "date": "01.02.2025 00:00:00",
        "ns": True,
        "TGmin": 1.0,  # 1 час ниже уставки
        "TGmax": 0,
        "TFault": 0,
        "Toff": 0,
        "QntHIP": 1.0,
        "QntP": 0
    }
    
    result = analyze_ns(test_record)
    
    print("=== Результат анализа ===")
    print(f"Есть НС: {result['has_ns']}")
    print(f"Обнаружено проблем: {len(result['detected_issues'])}")
    
    for issue in result["detected_issues"]:
        print(f"\nПоле: {issue['field']}")
        print(f"  Значение: {issue['value_hours']} ч")
        print(f"  Описание: {issue['description']}")
        print(f"  Возможные НС:")
        for ns in issue['possible_ns']:
            print(f"    - {ns}")
    
    print(f"\nСводка: {', '.join(result['summary'])}")
