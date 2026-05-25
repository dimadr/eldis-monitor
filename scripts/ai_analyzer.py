#!/usr/bin/env python3
"""
AI-анализатор данных теплосчётчика для отчётов ELDIS Monitor
Генерирует рекомендации для сервисных инженеров
"""

import json
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class AnalysisResult:
    """Результат анализа"""
    has_errors: bool
    error_count: int
    warnings: List[str]
    recommendations: List[str]
    severity: str  # critical, warning, ok


def analyze_device_data(readings: List[Dict], checks: Dict) -> AnalysisResult:
    """
    Основная функция анализа данных прибора
    
    Args:
        readings: Список показаний (из HTML таблицы)
        checks: Словарь результатов проверок из раздела "Проверки данных"
    
    Returns:
        AnalysisResult с рекомендациями
    """
    warnings = []
    recommendations = []
    error_count = 0
    
    # Анализ проверок
    if checks.get('mass_imbalance'):
        error_count += 1
        imbalance = checks['mass_imbalance']
        warnings.append(f"Небаланс масс {imbalance}% выходит за пределы нормы")
        
        if abs(imbalance) > 50:
            recommendations.append(
                "КРИТИЧНО: Подозрение на неисправность расходомера M2 или сбой архива. "
                "Требуется выезд для проверки датчиков и целостности данных."
            )
        else:
            recommendations.append(
                "Проверить настройки прибора и канал M2 на предмет утечек или "
                "некорректного учёта обратной массы."
            )
    
    if checks.get('negative_dt'):
        error_count += 1
        dt_value = checks['negative_dt']
        warnings.append(f"Отрицательная разница температур dt={dt_value}°C")
        
        recommendations.append(
            "ФИЗИЧЕСКАЯ НЕВОЗМОЖНОСТЬ: t2 (обратка) > t1 (подача). "
            "Проверить датчики температуры - возможна инверсия или неисправность t2."
        )
    
    if checks.get('ns_events'):
        ns_count = checks['ns_events']
        error_count += 1
        warnings.append(f"Обнаружено {ns_count} нештатных ситуаций")
        
        recommendations.append(
            f"Требуется изучение журнала NS - {ns_count} записей требуют анализа. "
            "Возможные причины: выход параметров за уставки, аварии, проблемы с датчиками."
        )
    
    # Анализ показаний (тепло)
    heat_readings = [r for r in readings if r.get('type') == 'heat']
    if heat_readings:
        avg_dt = sum(r.get('dt', 0) for r in heat_readings if r.get('dt')) / len(heat_readings)
        if avg_dt < 10:
            recommendations.append(
                f"Маленькая средняя dt={avg_dt:.1f}°C - возможно низкая нагрузка "
                "или проблемы с циркуляцией. Проверить насосное оборудование."
            )
        
        # Проверка на аномальные значения
        low_temp_days = sum(1 for r in heat_readings if r.get('t1', 0) < 70)
        if low_temp_days > 5:
            recommendations.append(
                f"Обнаружено {low_temp_days} дней с t1 < 70°C - нарушение температурного графика. "
                "Проверить работу котельной/теплового пункта."
            )
    
    # Анализ ГВС
    gvs_readings = [r for r in readings if r.get('type') == 'hotWater']
    if gvs_readings:
        low_temp_gvs = sum(1 for r in gvs_readings if r.get('t1', 0) < 60)
        if low_temp_gvs > 3:
            recommendations.append(
                f"Обнаружено {low_temp_gvs} дней с температурой ГВС < 60°C - "
                "нарушение требований к качеству ГВС."
            )
    
    # Определение критичности
    if error_count >= 3:
        severity = "critical"
    elif error_count > 0:
        severity = "warning"
    else:
        severity = "ok"
    
    return AnalysisResult(
        has_errors=error_count > 0,
        error_count=error_count,
        warnings=warnings,
        recommendations=recommendations,
        severity=severity
    )


def format_analysis_html(result: AnalysisResult) -> str:
    """Форматирование результата для HTML"""
    if result.severity == "ok":
        return "<p>Все показания в норме. Отклонений не выявлено.</p>"
    
    html = '<div style="color: #721c24;">'
    
    if result.severity == "critical":
        html += '<p><strong>⚠️ КРИТИЧЕСКАЯ СИТУАЦИЯ</strong> - требуется срочный выезд</p>'
    elif result.severity == "warning":
        html += '<p><strong>⚠️ ВНИМАНИЕ</strong> - обнаружены отклонения</p>'
    
    html += '<ul>'
    for rec in result.recommendations:
        html += f'<li style="margin-bottom: 8px;">{rec}</li>'
    html += '</ul>'
    
    html += '</div>'
    return html


def generate_service_report(checks: Dict, readings: List[Dict]) -> str:
    """
    Генерирует отчёт для сервисных инженеров
    
    Args:
        checks: Результаты проверок из HTML
        readings: Показания из таблицы
    
    Returns:
        Текст отчёта
    """
    result = analyze_device_data(readings, checks)
    
    if result.severity == "ok":
        return "Объект работает в штатном режиме."
    
    report = []
    
    if result.severity == "critical":
        report.append("🚨 ТРЕБУЕТСЯ СРОЧНОЕ ВМЕШАТЕЛЬСТВО")
    else:
        report.append("⚠️ ТРЕБУЕТСЯ ПРОВЕРКА")
    
    report.append("")
    
    for rec in result.recommendations:
        report.append(f"• {rec}")
    
    return "\n".join(report)


def parse_html_checks(checks_html: Dict) -> Dict:
    """
    Парсит данные из HTML проверок в структуру для анализа
    
    Args:
        checks_html: Словарь с данными проверок из HTML
    
    Returns:
        Подготовленный словарь для анализатора
    """
    parsed = {}
    
    # Небаланс масс
    mass_balance_text = checks_html.get('mass_imbalance', '')
    if 'error' in mass_balance_text.lower():
        import re
        match = re.search(r'([-\d.]+)%', mass_balance_text)
        if match:
            parsed['mass_imbalance'] = float(match.group(1))
    
    # Отрицательная dt
    dt_text = checks_html.get('negative_dt', '')
    if 'error' in dt_text.lower():
        import re
        match = re.search(r'([-\d.]+)°C', dt_text)
        if match:
            parsed['negative_dt'] = float(match.group(1))
    
    # NS события
    ns_text = checks_html.get('ns_events', '')
    if 'error' in ns_text.lower():
        import re
        match = re.search(r'(\d+)\s*записей', ns_text)
        if match:
            parsed['ns_events'] = int(match.group(1))
    
    return parsed


# Пример использования
if __name__ == "__main__":
    # Тестовые данные (как в отчёте ВКТ-7)
    test_checks = {
        'mass_imbalance': -97.94,
        'negative_dt': -0.2,
        'ns_events': 2
    }
    
    test_readings = []
    
    result = analyze_device_data(test_readings, test_checks)
    
    print("=== AI Анализ ===")
    print(f"Уровень: {result.severity.upper()}")
    print(f"Ошибок: {result.error_count}")
    print()
    print("Рекомендации:")
    for rec in result.recommendations:
        print(f"  • {rec}")