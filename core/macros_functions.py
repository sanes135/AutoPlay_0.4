import pynput
import threading
import time
from typing import Tuple, Union


class MacrosFunctions:
    """
    Набор функций для управления мышью и клавиатурой через pynput.
    Предназначен для передачи в глобальное пространство макроса.

    Особенности реализации:
    - все методы безопасны: неверные имена клавиш/кнопок не роняют макрос,
      а молча приводятся к разумному значению;
    - зажатые клавиши/кнопки отслеживаются и гарантированно отпускаются
      в release_all() (вызывается при остановке макроса);
    - методы потокобезопасны (одна блокировка на экземпляр).
    """

    def __init__(self):
        self._keyboard = pynput.keyboard.Controller()
        self._mouse = pynput.mouse.Controller()
        self._kb_key = pynput.keyboard.Key

        self._ru_to_en = {
            'й': 'q', 'ц': 'w', 'у': 'e', 'к': 'r', 'е': 't', 'н': 'y',
            'г': 'u', 'ш': 'i', 'щ': 'o', 'з': 'p', 'х': '[', 'ъ': ']',
            'ф': 'a', 'ы': 's', 'в': 'd', 'а': 'f', 'п': 'g', 'р': 'h',
            'о': 'j', 'л': 'k', 'д': 'l', 'ж': ';', 'э': "'",
            'я': 'z', 'ч': 'x', 'с': 'c', 'м': 'v', 'и': 'b', 'т': 'n',
            'ь': 'm', 'б': ',', 'ю': '.', 'ё': '`',
            'Й': 'Q', 'Ц': 'W', 'У': 'E', 'К': 'R', 'Е': 'T', 'Н': 'Y',
            'Г': 'U', 'Ш': 'I', 'Щ': 'O', 'З': 'P', 'Х': '{', 'Ъ': '}',
            'Ф': 'A', 'Ы': 'S', 'В': 'D', 'А': 'F', 'П': 'G', 'Р': 'H',
            'О': 'J', 'Л': 'K', 'Д': 'L', 'Ж': ':', 'Э': '"',
            'Я': 'Z', 'Ч': 'X', 'С': 'C', 'М': 'V', 'И': 'B', 'Т': 'N',
            'Ь': 'M', 'Б': '<', 'Ю': '>'
        }

        # Состояние зажатых клавиш/кнопок — нужно для гарантированного
        # освобождения при остановке макроса (release_all).
        self._held_keys = set()
        self._held_buttons = set()
        self._lock = threading.RLock()

        self.macros_functions = {
            # Клавиатура
            "key_press": self.key_press,
            "key_release": self.key_release,
            "key_tap": self.key_tap,
            "write": self.write,
            # Мышь
            "mouse_click": self.mouse_click,
            "mouse_press": self.mouse_press,
            "mouse_release": self.mouse_release,
            "mouse_move": self.mouse_move,
            "mouse_drag": self.mouse_drag,
            "mouse_position": self.mouse_position,
            "mouse_scroll": self.mouse_scroll,
            # Сервисные
            "release_all": self.release_all,
        }

    # ================= СЕРВИСНЫЕ =================
    def release_all(self) -> None:
        """Отпускает все зажатые этим экземпляром клавиши и кнопки мыши."""
        with self._lock:
            for key in list(self._held_keys):
                try:
                    self._keyboard.release(key)
                except Exception:
                    pass
            self._held_keys.clear()
            for btn in list(self._held_buttons):
                try:
                    self._mouse.release(btn)
                except Exception:
                    pass
            self._held_buttons.clear()

    def _resolve_key(self, key) -> Union[str, pynput.keyboard.Key]:
        """Внутренний метод: преобразует строковое название клавиши в формат pynput.

        Принимает также готовые объекты pynput.keyboard.Key — они возвращаются как есть.
        Неизвестные строки безопасно приводятся к нижнему регистру.
        """
        if not isinstance(key, str):
            return key

        key_lower = key.lower()
        special_keys = {
            'space': self._kb_key.space, 'enter': self._kb_key.enter, 'tab': self._kb_key.tab,
            'backspace': self._kb_key.backspace, 'delete': self._kb_key.delete, 'esc': self._kb_key.esc,
            'shift': self._kb_key.shift, 'ctrl': self._kb_key.ctrl, 'alt': self._kb_key.alt,
            'cmd': self._kb_key.cmd, 'win': self._kb_key.cmd, 'caps_lock': self._kb_key.caps_lock,
            'num_lock': self._kb_key.num_lock, 'scroll_lock': self._kb_key.scroll_lock, 'pause': self._kb_key.pause,
            'insert': self._kb_key.insert, 'home': self._kb_key.home, 'end': self._kb_key.end,
            'page_up': self._kb_key.page_up, 'page_down': self._kb_key.page_down,
            'up': self._kb_key.up, 'down': self._kb_key.down, 'left': self._kb_key.left, 'right': self._kb_key.right,
        }
        for i in range(1, 13):
            special_keys[f'f{i}'] = getattr(self._kb_key, f'f{i}')

        if key_lower in special_keys:
            return special_keys[key_lower]

        # Если символ один и есть в карте раскладки, подставляем латинский аналог
        if len(key) == 1 and key_lower in self._ru_to_en:
            return self._ru_to_en[key_lower]

        return key_lower

    def _resolve_mouse_button(self, button) -> pynput.mouse.Button:
        """Преобразует строку 'left'/'right'/'middle' в объект кнопки pynput.

        Неизвестные значения безопасно заменяются на левую кнопку.
        """
        if isinstance(button, pynput.mouse.Button):
            return button
        btn_map = {
            'left': pynput.mouse.Button.left,
            'right': pynput.mouse.Button.right,
            'middle': pynput.mouse.Button.middle
        }
        try:
            return btn_map.get(str(button).lower(), pynput.mouse.Button.left)
        except Exception:
            return pynput.mouse.Button.left

    # ================= КЛАВИАТУРА =================
    def key_press(self, key: str) -> None:
        """Зажимает клавишу и удерживает её до вызова key_release(key)."""
        resolved = self._resolve_key(key)
        with self._lock:
            self._held_keys.add(resolved)
        self._keyboard.press(resolved)

    def key_release(self, key: str) -> None:
        """Отпускает ранее зажатую клавишу."""
        resolved = self._resolve_key(key)
        with self._lock:
            self._held_keys.discard(resolved)
        self._keyboard.release(resolved)

    def key_tap(self, key: str, delay: float = 0.0) -> None:
        """Мгновенно нажимает и отпускает клавишу. Аналог обычного нажатия."""
        resolved = self._resolve_key(key)
        self._keyboard.press(resolved)
        try:
            if delay > 0:
                time.sleep(delay)
        finally:
            # клавиша обязана быть отпущена даже при ошибке/прерывании задержки
            self._keyboard.release(resolved)

    def write(self, text: str, interval: float = 0.0) -> None:
        """Печатает текст посимвольно. interval - задержка между символами в секундах."""
        if not isinstance(text, str):
            text = str(text)
        for char in text:
            self._keyboard.type(char)
            if interval > 0:
                time.sleep(interval)

    # ================= МЫШЬ =================
    def mouse_click(self, button: str = 'left') -> None:
        """Однократный клик кнопкой мыши ('left', 'right', 'middle')."""
        btn = self._resolve_mouse_button(button)
        self._mouse.click(btn)

    def mouse_press(self, button: str = 'left') -> None:
        """Зажимает кнопку мыши."""
        btn = self._resolve_mouse_button(button)
        with self._lock:
            self._held_buttons.add(btn)
        try:
            self._mouse.press(btn)
        except Exception:
            with self._lock:
                self._held_buttons.discard(btn)
            raise

    def mouse_release(self, button: str = 'left') -> None:
        """Отпускает зажатую кнопку мыши."""
        btn = self._resolve_mouse_button(button)
        with self._lock:
            self._held_buttons.discard(btn)
        self._mouse.release(btn)

    def mouse_scroll(self, dx: int, dy: int) -> None:
        """Прокручивает колесо мыши: dy>0 — вверх, dy<0 — вниз."""
        try:
            dx, dy = int(dx), int(dy)
        except (TypeError, ValueError):
            return  # некорректные аргументы — молча игнорируем, макрос живёт
        self._mouse.scroll(dx, dy)

    def mouse_move(self, x: int, y: int, absolute: bool = False) -> None:
        """
        Перемещает курсор.
        absolute=True  -> x, y это абсолютные координаты на экране.
        absolute=False -> x, y это смещение относительно текущей позиции курсора.
        """
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            return  # некорректные координаты — без падения макроса
        if absolute:
            self._mouse.position = (x, y)
        else:
            self._mouse.move(x, y)

    def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.0) -> None:
        """
        Перетаскивание курсора из точки A в точку B с зажатой левой кнопкой.
        duration: время выполнения перетаскивания в секундах (0 = мгновенно).
        Кнопка гарантированно отпускается, даже если что-то пошло не так.
        """
        self.mouse_move(start_x, start_y, absolute=True)
        self.mouse_press('left')
        try:
            if duration > 0:
                steps = max(10, int(duration * 50))
                dx = (end_x - start_x) / steps
                dy = (end_y - start_y) / steps
                for _ in range(steps):
                    self._mouse.move(dx, dy)
                    time.sleep(duration / steps)
            else:
                self._mouse.position = (end_x, end_y)
        finally:
            self.mouse_release('left')

    def mouse_position(self) -> Tuple[int, int]:
        """Возвращает текущие координаты курсора в виде кортежа (x, y)."""
        return self._mouse.position
