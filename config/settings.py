import os
import threading

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


REGISTRY_PATH = r"Software\AutoKM"

# Фолбэк-хранилище настроек, когда реестр Windows недоступен (Linux/macOS)
FALLBACK_SETTINGS_FILE = os.path.join(
    os.path.expanduser("~"), ".autokm_settings.json"
)

# Кэш JSON-файла настроек: читаем диск один раз, дальше работаем в памяти.
_fallback_lock = threading.Lock()
_fallback_cache = None  # dict | None (None = ещё не загружен)

DEFAULT_SETTINGS = {
    "app_mode": "System",
    'color_theme': 'blue',
    "clicker_hotkey": "F6",
    "macro_hotkey": "F8",
    "macro_stop_hotkey": "F9",
    "font_size": 12,
    "recent_file": None,
}


def _load_fallback_settings():
    """Читает настройки из JSON-файла (используется, когда реестр недоступен).

    Результат кэшируется в памяти под блокировкой — диск читается один раз,
    дальнейшие обращения быстры и потокобезопасны.
    """
    global _fallback_cache
    import json
    with _fallback_lock:
        if _fallback_cache is not None:
            return dict(_fallback_cache)
        data = {}
        try:
            with open(FALLBACK_SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
        _fallback_cache = data
        return dict(data)


def _save_fallback_settings(data):
    """Атомарная запись JSON-настроек: сначала во временный файл, затем replace."""
    import json
    tmp = FALLBACK_SETTINGS_FILE + ".tmp"
    with _fallback_lock:
        _fallback_cache = dict(data)  # кэш всегда актуален после записи
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, FALLBACK_SETTINGS_FILE)
        except Exception as r:
            print(r)


def get_setting(name, default_value):
    """
    Универсальное получение настройки: из реестра, а при его недоступности —
    из JSON-файла. Возвращает default_value, если значение не найдено или пусто.
    """
    value = get_registry_value(name, default_value)
    if value in (None, "") and name in DEFAULT_SETTINGS:
        value = DEFAULT_SETTINGS[name]
    return value


def set_setting(name, value):
    """
    Универсальное сохранение настройки: в реестр, а при его недоступности —
    в JSON-файл.
    """
    if HAS_WINREG:
        set_registry_value(name, "" if value is None else value)
        return
    data = _load_fallback_settings()
    data[name] = value
    _save_fallback_settings(data)


MAX_RECENT_FILES = 10


def add_recent_file(path):
    """
    Добавляет путь к файлу макроса в список последних файлов (recent_file).
    Хранится как строка путей, разделённых ';': самые новые — в начале.
    Пути с ';' из списка исключаются (разделитель ломает формат хранения).
    """
    if not path:
        return
    try:
        path = os.path.abspath(path)
    except Exception:
        return
    if ";" in path:
        return  # не можем корректно сохранить такой путь
    raw = get_registry_value("recent_file", "") or ""
    recent = [p for p in raw.split(";") if p.strip() and ";" not in p]
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    set_registry_value("recent_file", ";".join(recent[:MAX_RECENT_FILES]))


def get_recent_files():
    """Возвращает список последних файлов (существующие пути)."""
    raw = get_registry_value("recent_file", "") or ""
    result = []
    for p in raw.split(";"):
        p = p.strip()
        if not p:
            continue
        try:
            if os.path.isfile(p):
                result.append(p)
        except Exception:
            continue
    return result


def get_registry_value(name, default_value):
    """
    Получает значение из реестра. Возвращает default_value, если не найдено.
    """
    if not HAS_WINREG:
        return _load_fallback_settings().get(name, default_value)
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_PATH,
            0,
            winreg.KEY_READ
        ) as key:
            value, regtype = winreg.QueryValueEx(key, name)
        if isinstance(default_value, int) and isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default_value
        return value
    except FileNotFoundError:
        # значения ещё нет — создаём дефолтное (первый запуск)
        set_registry_value(name, default_value)
    except Exception:
        pass  # любые проблемы с реестром не должны ронять приложение
    return default_value


def set_registry_value(name, value):
    """
    Сохраняет значение в реестр (или в JSON-файл, если реестр недоступен).
    """
    if not HAS_WINREG:
        data = _load_fallback_settings()
        data[name] = value
        _save_fallback_settings(data)
        return
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))
    except Exception:
        pass  # недоступный/защищённый ключ не должен ронять приложение


def add_default_settings():
    """Создаёт отсутствующие значения настроек по умолчанию (первый запуск)."""
    if not HAS_WINREG or winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_READ) as key:
            existing_keys = set()
            i = 0
            while True:
                try:
                    name, value, value_type = winreg.EnumValue(key, i)
                    existing_keys.add(name)
                    i += 1
                except OSError:
                    break

        for setting_name in DEFAULT_SETTINGS:
            if setting_name not in existing_keys:
                set_registry_value(setting_name, DEFAULT_SETTINGS.get(setting_name))
    except FileNotFoundError:
        # ключа ещё нет — создаём все дефолты (CreateKey сам создаст путь)
        for setting_name in DEFAULT_SETTINGS:
            set_registry_value(setting_name, DEFAULT_SETTINGS.get(setting_name))
    except Exception:
        pass  # молча игнорируем проблемы реестра — есть дефолты в коде