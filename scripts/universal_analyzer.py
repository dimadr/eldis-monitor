#!/usr/bin/env python3
"""
Универсальный AI-анализатор для приборов учета
Поддерживает ВКТ-5, ВКТ-7, ВКТ-9, ВКГ и др. на основе мануалов
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


BASE_DIR = Path(__file__).parent.parent


@dataclass
class DiagnosticSituation:
    """Диагностируемая ситуация (ДС)"""
    code: str
    name: str
    description: str
    cause: str
    solution: str


@dataclass
class CheckResult:
    """Результат проверки"""
    name: str
    value: str
    is_error: bool


@dataclass
class AnalysisResult:
    """Результат анализа"""
    device_name: str
    has_errors: bool
    errors: List[str]
    recommendations: List[str]
    severity: str


class DeviceManual:
    """Загружает и парсит мануал прибора"""
    
    def __init__(self, name: str, base_path: Path):
        self.name = name
        self.diagnostics: List[DiagnosticSituation] = []
        self.errors: Dict[str, str] = {}
        
        # Попробовать загрузить MD файл
        md_path = base_path / f"{name}.md"
        if md_path.exists():
            self._parse_md(md_path)
        
        # Также попробовать txt
        txt_path = base_path / f"{name}.txt"
        if txt_path.exists() and not self.diagnostics:
            self._parse_txt(txt_path)
    
    def _parse_md(self, path: Path):
        """Парсинг markdown версии мануала"""
        content = path.read_text(encoding='utf-8')
        
        # Ищем диагностируемые ситуации (ДС)
        patterns = [
            r'[Дд][Сс]\s*(\d+)[^\n]*([^\n]{0,50})',
            r'Таблица\s+Б\d+.*?(\d+)[^\n]*([^\n]{0,60})',
        ]
        
        for match in re.finditer(r'[Дд][Сс]\s*(\d+)[:\.\s]+([^\n]{3,80})', content):
            code = match.group(1)
            desc = match.group(2).strip()
            
            if len(desc) > 5:
                self.diagnostics.append(DiagnosticSituation(
                    code=code,
                    name=f"ДС {code}",
                    description=desc,
                    cause="См. мануал",
                    solution="Требуется диагностика"
                ))
    
    def _parse_txt(self, path: Path):
        """Парсинг текстовой версии мануала"""
        content = path.read_text(encoding='utf-8', errors='ignore')
        
        for match in re.finditer(r'[Дд][Сс]\s*(\d+)[:\.\s]+([^\n]{3,80})', content):
            code = match.group(1)
            desc = match.group(2).strip()
            
            if len(desc) > 5:
                self.diagnostics.append(DiagnosticSituation(
                    code=code,
                    name=f"ДС {code}",
                    description=desc,
                    cause="См. мануал",
                    solution="Требуется диагностика"
                ))


class UniversalAnalyzer:
    """Универсальный анализатор для всех приборов учета"""
    
    # Маппинг кодов моделей на названия приборов
    MODEL_CODES = {
        '20002': 'ВКТ-7',
        '20001': 'ВКТ-5',
        '20003': 'ВКТ-9',
        '20100': 'ВКГ-2',
        '20101': 'ВКГ-3Т',
        '20102': 'ВКГ-3Д',
        '20310': 'СПТ-940',
        '20311': 'СПТ-941',
        '20312': 'СПТ-942',
        '20313': 'СПТ-943',
        '20314': 'СПТ-944',
        '20320': 'СПТ-961',
        '20321': 'СПТ-962',
        '20322': 'СПТ-963',
        '21100': 'ТВ7',
        '21050': 'ТСРВ-026',
        '21051': 'ТСРВ-026М',
    }
    
    # Маппинг названий приборов на PDF файлы
    DEVICE_PDF_MAP = {
        'ВКТ-7': 'ВКТ-7.pdf',
        'ВКТ-5': 'ВКТ-5.pdf',
        'ВКТ-9': 'ВКТ-9.pdf',
        'ВКГ-2': 'ВКГ-2.pdf',
        'ВКГ-3Т': 'ВКГ-3Т.pdf',
        'ВКГ-3Д': 'ВКГ-3Д.pdf',
        'СПТ-940': 'СПТ-940.pdf',
        'СПТ-941': 'СПТ-941.pdf',
        'СПТ-942': 'СПТ-942.pdf',
        'СПТ-943': 'СПТ-943.pdf',
        'СПТ-944': 'СПТ-944.pdf',
        'СПТ-961': 'СПТ-961.pdf',
        'СПТ-962': 'СПТ-962.pdf',
        'СПТ-963': 'СПТ-963.pdf',
        'ТВ7': 'ТВ7.pdf',
        'ТСРВ-026': 'ТСРВ-026_1.pdf',
        'ТСРВ-026М': 'ТСРВ-026М.pdf',
    }
    
    # Дополнительные коды из ns_catalog.json
    EXTRA_CODES = {
        '20002': 'ВКТ-7',
    }
    
    def __init__(self):
        self.manuals_path = BASE_DIR / 'Base' / 'Теплоком' / 'MD'
        self.pdf_path = BASE_DIR / 'Base' / 'PDF'
        
        # Специфичные правила для разных приборов
        self.device_rules: Dict[str, Dict] = {
            'ВКТ-7': {
                'checks': {
                    'mass_imbalance': {
                        'ds_code': '04',
                        'name': 'Контроль баланса массы',
                        'first_check': 'Проверить уставку контроля баланса (параметр КМ и БМ). Для открытых систем КМ=3, для закрытых КМ=4.',
                        'description': 'Небаланс масс M1-M2 превышает уставку БМ'
                    },
                    'negative_dt': {
                        'ds_code': '02',
                        'name': 't1 < t2',
                        'first_check': 'Проверить датчики температуры - возможна инверсия (перепутаны местами) или неисправность t2.',
                        'description': 'Температура подачи меньше температуры обратки'
                    },
                    'low_dt': {
                        'ds_code': '09',
                        'name': 'Контроль dT',
                        'first_check': 'Проверить насосное оборудование и нагрузку - возможна низкая циркуляция.',
                        'description': 'Разность температур меньше минимума'
                    },
                    'ns_events': {
                        'ds_code': 'various',
                        'name': 'Нештатные ситуации',
                        'first_check': 'Извлечь коды ошибок из журнала NS (01-04 - аппаратные, 10-11 - температура, 20-30 - расход/масса).',
                        'description': 'Обнаружены нештатные ситуации в архиве'
                    },
                    'no_mass': {
                        'ds_code': '03',
                        'name': 'Отсутствие массы',
                        'first_check': 'Проверить расходомеры M1 и M2 - отсутствие сигнала или неисправность.',
                        'description': 'Масса равна нулю при положительной температуре'
                    }
                }
            },
            'ВКТ-5': {
                'checks': {
                    'mass_imbalance': {
                        'ds_code': '04',
                        'name': 'Контроль баланса массы',
                        'first_check': 'Проверить параметры КМ и БМ в настройках',
                        'description': 'Небаланс масс превышает норму'
                    },
                    'negative_dt': {
                        'ds_code': '02',
                        'name': 't1 < t2',
                        'first_check': 'Проверить подключение датчиков температуры',
                        'description': 'Инверсия температур'
                    }
                }
            },
            'ВКТ-9': {
                'checks': {
                    'mass_imbalance': {
                        'ds_code': '04',
                        'name': 'Контроль баланса',
                        'first_check': 'Проверить параметры КМ и БМ в настройках прибора',
                        'description': 'Небаланс масс'
                    },
                    'negative_dt': {
                        'ds_code': '02',
                        'name': 'Инверсия t1/t2',
                        'first_check': 'Проверить подключение датчиков температуры',
                        'description': 't1 < t2'
                    }
                }
            },
            'СПТ-941': {
                'checks': {
                    'mass_imbalance': {
                        'ds_code': '04',
                        'name': 'Контроль баланса',
                        'first_check': 'Проверить настройку каналов M1/M2 и уставку небаланса',
                        'description': 'Превышение небаланса масс'
                    },
                    'negative_dt': {
                        'ds_code': '02',
                        'name': 'Инверсия температур',
                        'first_check': 'Проверить датчики t1 и t2 на предмет перепутывания',
                        'description': 'Температура подачи ниже обратки'
                    },
                    'ns_events': {
                        'ds_code': 'various',
                        'name': 'Нештатные ситуации',
                        'first_check': 'Извлечь коды из журнала НС',
                        'description': 'Зафиксированы НС'
                    }
                }
            },
            'СПТ-961': {
                'checks': {
                    'mass_imbalance': {
                        'ds_code': '04',
                        'name': 'Контроль баланса',
                        'first_check': 'Проверить расходомеры и настройки баланса',
                        'description': 'Небаланс масс'
                    },
                    'negative_dt': {
                        'ds_code': '02',
                        'name': 'Инверсия',
                        'first_check': 'Проверить датчики температуры',
                        'description': 't1 < t2'
                    }
                }
            },
            'ТВ7': {
                'checks': {
                    'mass_imbalance': {
                        'ds_code': '04',
                        'name': 'Небаланс',
                        'first_check': 'Проверить расходомеры M1 и M2',
                        'description': 'Небаланс масс'
                    },
                    'negative_dt': {
                        'ds_code': '02',
                        'name': 'Инверсия',
                        'first_check': 'Проверить датчики температуры',
                        'description': 't1 < t2'
                    }
                }
            }
        }
    
    def get_device_name(self, device_code: str) -> Optional[str]:
        """Определить название прибора по коду"""
        return self.MODEL_CODES.get(device_code) or self.EXTRA_CODES.get(device_code)
    
    def get_manual_path(self, device_name: str) -> Optional[Path]:
        """Получить путь к мануалу прибора"""
        pdf_name = self.DEVICE_PDF_MAP.get(device_name)
        if pdf_name:
            return self.pdf_path / pdf_name
        return None
    
    def analyze(self, device_code: str, device_name: str, checks: Dict) -> AnalysisResult:
        """
        Основная функция анализа
        
        Args:
            device_code: Код модели прибора (например, 20002)
            device_name: Название прибора (например, ВКТ-7)
            checks: Результаты проверок из HTML
        """
        # Определить название если не передано
        if not device_name:
            device_name = self.get_device_name(device_code) or 'Unknown'
        
        errors = []
        recommendations = []
        
        # Получить правила для прибора
        rules = self.device_rules.get(device_name, {})
        
        # Анализ каждой ошибки
        if 'mass_imbalance' in checks and checks['mass_imbalance'] is not None:
            val = checks['mass_imbalance']
            if abs(val) > 2:  # Порог для ВКТ-7
                errors.append(f"Небаланс масс: {val}%")
                
                rule = rules.get('checks', {}).get('mass_imbalance', {})
                recommendations.append(
                    f"1️⃣ {rule.get('first_check', 'Проверить настройки баланса')}"
                )
        
        if 'negative_dt' in checks and checks['negative_dt'] is not None:
            val = checks['negative_dt']
            if val < 2:  # dt должна быть >= 2
                errors.append(f"Отрицательная dt: {val}°C")
                
                rule = rules.get('checks', {}).get('negative_dt', {})
                recommendations.append(
                    f"2️⃣ {rule.get('first_check', 'Проверить датчики температуры')}"
                )
        
        if 'ns_events' in checks and checks['ns_events']:
            count = checks['ns_events']
            errors.append(f"Нештатных ситуаций: {count}")
            
            rule = rules.get('checks', {}).get('ns_events', {})
            recommendations.append(
                f"3️⃣ {rule.get('first_check', 'Изучить журнал NS')}"
            )
        
        # Определение критичности
        if len(errors) >= 3:
            severity = 'critical'
        elif len(errors) > 0:
            severity = 'warning'
        else:
            severity = 'ok'
        
        return AnalysisResult(
            device_name=device_name,
            has_errors=len(errors) > 0,
            errors=errors,
            recommendations=recommendations,
            severity=severity
        )
    
    def format_html(self, result: AnalysisResult) -> str:
        """Форматирование результата для HTML"""
        if result.severity == 'ok':
            return '<p>Все показания в норме. Отклонений не выявлено.</p>'
        
        html = f'<p><strong>'
        if result.severity == 'critical':
            html += '🚨 КРИТИЧЕСКАЯ СИТУАЦИЯ'
        else:
            html += '⚠️ ВНИМАНИЕ'
        html += f'</strong> - требуется проверка ({result.device_name})</p>'
        
        html += '<ul>'
        for rec in result.recommendations:
            html += f'<li style="margin-bottom: 8px;">{rec}</li>'
        html += '</ul>'
        
        return html


def create_analyzer() -> UniversalAnalyzer:
    """Создать экземпляр анализатора"""
    return UniversalAnalyzer()


if __name__ == "__main__":
    analyzer = create_analyzer()
    
    # Тест для ВКТ-7
    print("=== Тест для ВКТ-7 ===")
    result = analyzer.analyze('20002', 'ВКТ-7', {
        'mass_imbalance': -97.94,
        'negative_dt': -0.2,
        'ns_events': 2
    })
    
    print(f"Прибор: {result.device_name}")
    print(f"Уровень: {result.severity.upper()}")
    print(f"Ошибок: {len(result.errors)}")
    for rec in result.recommendations:
        print(rec)