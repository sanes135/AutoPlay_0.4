import customtkinter as ctk
import tkinter as tk
from threading import Thread, Event
from time import sleep
import pynput
from config.settings import get_registry_value, set_registry_value
from utils.helpers import resource_path

ctk.set_appearance_mode(get_registry_value('app_mode', 'System')) # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme(get_registry_value('color_theme', 'blue')) # Themes: "blue" (standard), "green", "dark-blue"


class InstructionsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Дочернее окно")

        x, y = parent.winfo_x(), parent.winfo_y()
        if (x + 900) >= 1980:
            x -= 1000
        self.geometry(f"300x200+{x+500}+{y+200}")
        self.resizable(width=False, height=False)
        self.grab_set()

        self.current_app_mode = ctk.StringVar(value=get_registry_value('app_mode', 'System'))
        self.current_color_theme = ctk.StringVar(value=get_registry_value('color_theme', 'blue'))

        ctk.CTkLabel(self, text="Appearance mode").pack(anchor="w", padx=10, pady=(5, 0))
        mouse_button_combo = ctk.CTkComboBox(self, values=["System", "Dark", "Light"], variable=self.current_app_mode, command=self.set_app_mode)
        mouse_button_combo.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(self, text="Color theme (need restart)").pack(anchor="w", padx=10, pady=(5, 0))
        mouse_button_combo = ctk.CTkComboBox(self, values=["blue", "green", "dark-blue", 'red'], variable=self.current_color_theme, command=self.set_color_theme)
        mouse_button_combo.pack(fill="x", padx=10, pady=(0, 5))

    def set_app_mode(self, mode):
        try:
            ctk.set_appearance_mode(mode)
        except Exception:
            pass
        set_registry_value('app_mode', mode)

    def set_color_theme(self, theme):
        try:
            ctk.set_default_color_theme(theme)
        except Exception:
            pass
        set_registry_value('color_theme', theme)

class AutoClickerWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        window_width = 420
        window_height = 450
        self.title("AutoKM 0.4")
        self.geometry(f"{window_width}x{window_height}")
        self.resizable(width=False, height=False)
        self.available_keys = (
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
            "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S",
            "T", "U", "V", "W", "X", "Y", "Z",
            "ALT", "CTRL", "TAB", "SHIFT", "SPACE",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"
        )

        self.hours_var = ctk.IntVar(value=0)
        self.minutes_var = ctk.IntVar(value=0)
        self.seconds_var = ctk.IntVar(value=1)
        self.milliseconds_var = ctk.IntVar(value=0)
        self.total_time = self._read_total_time()

        self.use_mouse_var = ctk.BooleanVar(value=True)
        self.use_keyboard_var = ctk.BooleanVar(value=False)

        self.current_click_key = ctk.StringVar(value='SPACE')
        self.current_mouse_button = ctk.StringVar(value="Left")
        self.current_hotkey = ctk.StringVar(value="F6")

        self.pynput_button = pynput.mouse.Button.left
        self.pynput_key = pynput.keyboard.Key.space
        # Один переиспользуемый контроллер — не создаём объекты на каждый тик
        self._mouse_ctrl = pynput.mouse.Controller()
        self._keyboard_ctrl = pynput.keyboard.Controller()
        self.listener = None
        self._start_hotkey_listener(get_registry_value('clicker_hotkey', 'F6'))

        self.clicker_is_working = False
        self._closing = False

        self.create_widgets()

        self.stop_flag = Event()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------
    def _read_int(self, var):
        """Безопасное чтение IntVar: некорректный ввод не роняет запуск."""
        try:
            return int(var.get())
        except (tk.TclError, TypeError, ValueError):
            return 0

    def _read_total_time(self):
        hours = max(0, self._read_int(self.hours_var))
        minutes = max(0, self._read_int(self.minutes_var))
        seconds = max(0, self._read_int(self.seconds_var))
        millis = max(0, self._read_int(self.milliseconds_var))
        return hours * 3600 + minutes * 60 + seconds + millis / 1000

    def _start_hotkey_listener(self, button):
        """(Пере)регистрирует глобальный хоткей автокликера; ошибки не фатальны."""
        key = str(button).strip().upper() if button else ""
        if not key:
            return
        try:
            if len(key) > 1:
                mapping = {f'<{key.lower()}>': self.toggle_clicker}
            else:
                mapping = {key.lower(): self.toggle_clicker}
            listener = pynput.keyboard.GlobalHotKeys(mapping)
            listener.daemon = True
            listener.start()
        except Exception:
            return  # хоткей недоступен — кликером можно управлять кнопками UI
        self.listener = listener
        try:
            set_registry_value('clicker_hotkey', key)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def create_widgets(self):
        """Создание и размещение виджетов."""
        main_frame = ctk.CTkFrame(master=self)
        main_frame.pack(padx=10, pady=10, fill="both", expand=True)

        time_input_frame = ctk.CTkFrame(master=main_frame)
        time_input_frame.pack(fill="x", padx=5, pady=(5, 0))

        ctk.CTkEntry(time_input_frame, textvariable=self.hours_var, width=50).pack(side="left", padx=(5, 2))
        ctk.CTkLabel(time_input_frame, text="hours", width=30).pack(side="left", padx=3)
        ctk.CTkEntry(time_input_frame, textvariable=self.minutes_var, width=50).pack(side="left", padx=2)
        ctk.CTkLabel(time_input_frame, text="mins", width=30).pack(side="left", padx=3)
        ctk.CTkEntry(time_input_frame, textvariable=self.seconds_var, width=50).pack(side="left", padx=2)
        ctk.CTkLabel(time_input_frame, text="secs", width=30).pack(side="left", padx=3)
        ctk.CTkEntry(time_input_frame, textvariable=self.milliseconds_var, width=50).pack(side="left", padx=2)
        ctk.CTkLabel(time_input_frame, text="mil-secs", width=30).pack(side="left", padx=3)

        buttons_frame = ctk.CTkFrame(master=main_frame)
        buttons_frame.pack(fill="x", padx=5, pady=10)

        self.start_button = ctk.CTkButton(buttons_frame, text="Start", command=self.start_clicked, height=60)
        self.start_button.pack(side="left", padx=5, expand=True, fill="x")

        self.stop_button = ctk.CTkButton(buttons_frame, text="Stop", command=self.stop_clicked, state="disabled", height=60)
        self.stop_button.pack(side="left", padx=5, expand=True, fill="x")

        settings_frame = ctk.CTkFrame(master=main_frame)
        settings_frame.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(settings_frame, text="Mouse click type").pack(anchor="w", padx=10, pady=(5, 0))
        mouse_button_combo = ctk.CTkComboBox(settings_frame, values=["Left", "Right", "Middle"], variable=self.current_mouse_button)
        mouse_button_combo.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(settings_frame, text="Keyboard click type").pack(anchor="w", padx=10, pady=(5, 0))
        keyboard_key_combo = ctk.CTkComboBox(settings_frame, values=self.available_keys, variable=self.current_click_key)
        keyboard_key_combo.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(settings_frame, text="Set hotkey").pack(anchor="w", padx=10, pady=(5, 0))
        hotkey_combo = ctk.CTkComboBox(settings_frame, values=self.available_keys, variable=self.current_hotkey, command=self.set_hotkey)
        hotkey_combo.pack(fill="x", padx=10, pady=(0, 5))

        input_method_frame = ctk.CTkFrame(master=main_frame)
        input_method_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkCheckBox(input_method_frame, text='Mouse', variable=self.use_mouse_var).pack(side="left", padx=10)
        ctk.CTkCheckBox(input_method_frame, text='Keyboard', variable=self.use_keyboard_var).pack(side="left", padx=10)

        self.status_label = ctk.CTkLabel(main_frame, text="Status: Off")
        self.status_label.pack(pady=5)

        bottom_frame = ctk.CTkFrame(master=main_frame)
        bottom_frame.pack(fill="x", padx=5, pady=(5, 10), side="bottom")

        ctk.CTkButton(bottom_frame, text="Написать макрос", command=self.macro_clicked).pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkButton(bottom_frame, text="Настройки", command=self.settings_clicked).pack(side="left", padx=5, expand=True, fill="x")

    # ------------------------------------------------------------------
    # Логика кликера
    # ------------------------------------------------------------------
    def click(self):
        interval = self.total_time
        try:
            use_mouse = bool(self.use_mouse_var.get())
            use_keyboard = bool(self.use_keyboard_var.get())
        except Exception:
            use_mouse, use_keyboard = True, False
        button = self.pynput_button
        key = self.pynput_key
        try:
            if interval > 0:
                # интервальный режим: цикл с мгновенной реакцией на Stop
                while not self.stop_flag.is_set():
                    try:
                        if use_mouse:
                            self._mouse_ctrl.click(button)
                        if use_keyboard:
                            self._keyboard_ctrl.tap(key)
                    except Exception:
                        break  # ввод недоступен — останавливаемся без падения потока
                    # сон по частям, чтобы Stop реагировал быстрее
                    remaining = interval
                    while remaining > 0 and not self.stop_flag.is_set():
                        step = min(0.05, remaining)
                        sleep(step)
                        remaining -= step
            elif interval == 0:
                # нулевой интервал считаем ошибкой ввода — ничего не делаем
                pass
            else:
                # отрицательный интервал — удержание клавиш до остановки
                try:
                    if use_mouse:
                        self._mouse_ctrl.press(button)
                    if use_keyboard:
                        self._keyboard_ctrl.press(key)
                    while not self.stop_flag.is_set():
                        sleep(0.05)
                    if use_mouse:
                        self._mouse_ctrl.release(button)
                    if use_keyboard:
                        self._keyboard_ctrl.release(key)
                except Exception:
                    pass
        finally:
            self.clicker_is_working = False
            # возврат UI в исходное состояние из потока кликера — через after()
            try:
                self.after(0, self._ui_reset_stopped)
            except Exception:
                pass  # окно уже закрыто

    def _ui_reset_stopped(self):
        """Вызывается в потоке Tk: включить кнопку Start после самоостановки."""
        try:
            self.stop_button.configure(state="disabled")
            self.start_button.configure(state="normal")
            self.status_label.configure(text="Status: Off")
        except Exception:
            pass

    def toggle_clicker(self):
        """Хоткей: запуск/остановка. Все обращения к UI — в потоке Tk."""
        try:
            self.after(0, self._toggle_in_ui_thread)
        except Exception:
            pass  # окно закрыто

    def _toggle_in_ui_thread(self):
        if self.clicker_is_working:
            self.stop_clicked()
        else:
            self.start_clicked()

    def start_clicked(self):
        if self.clicker_is_working:
            return  # защита от двойного запуска (хоткей + кнопка)
        if not (self.use_mouse_var.get() or self.use_keyboard_var.get()):
            self.status_label.configure(text="Status: выберите мышь или клавиатуру")
            return

        self.total_time = self._read_total_time()

        try:
            name = self.current_mouse_button.get().strip().lower()
            self.pynput_button = getattr(pynput.mouse.Button, name)
        except Exception:
            self.pynput_button = pynput.mouse.Button.left
        key_name = self.current_click_key.get().strip()
        try:
            if len(key_name) > 1:
                self.pynput_key = getattr(pynput.keyboard.Key, key_name.lower())
            else:
                self.pynput_key = key_name.lower()
        except Exception:
            self.pynput_key = key_name.lower() if key_name else pynput.keyboard.Key.space

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_label.configure(text="Status: On")

        self.stop_flag.clear()
        self.clicker_is_working = True
        Thread(target=self.click, daemon=True).start()

    def stop_clicked(self):
        self.stop_flag.set()
        self.stop_button.configure(state="disabled")
        self.start_button.configure(state="normal")
        self.status_label.configure(text="Status: Off")

    def set_hotkey(self, button):
        old = self.listener
        self.listener = None
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
        self._start_hotkey_listener(button)

    def macro_clicked(self):
        from ui.macro_window import MacroEditorWindow
        self.withdraw()
        MacroEditorWindow(self).iconbitmap(resource_path('tea.ico'))

    def settings_clicked(self):
        InstructionsWindow(self)

    def on_close(self):
        """Корректное завершение работы при закрытии окна."""
        if self._closing:
            return
        self._closing = True
        self.stop_flag.set()
        self.clicker_is_working = False
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None
        try:
            self.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    app = AutoClickerWindow()
    app.wm_attributes("-topmost", True)
    app.mainloop()
