import os
import threading
import time
import traceback

import customtkinter as ctk
from tkinter import messagebox

try:
    import pynput
    HAS_PYNPUT = True
except Exception:
    HAS_PYNPUT = False

from config.settings import get_setting, set_setting
from core.macros_functions import MacrosFunctions
from ui.tabs.code_tab import CodeTabCTk
from ui.tabs.instructions_tab import InstructionsTabCTk
from ui.tabs.methods_tab import MethodsTab

class MacroStop(Exception):
    """Бросается внутри макроса, когда пользователь нажал остановку."""
    pass


class MacroEditorWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.title("Редактор макросов")
        self.geometry("900x650")
        self.grab_set()

        # Глобальный листенер хоткеев для запуска/остановки макроса
        self._hotkey_listener = None          # pynput.keyboard.Listener
        self._macro_hotkeys = {}              # {'<f8>': callback}
        self.macro_thread = None
        self.macro_stop_event = threading.Event()
        self.macro_started_at = 0.0
        self._release_fn = None               # MacrosFunctions.release_all текущего запуска

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        tab_code = self.tabview.add("Код")
        tab_instr = self.tabview.add("Инструкция")
        tab_methods = self.tabview.add("Методы")

        self.code_tab = CodeTabCTk(tab_code, macro_window=self)
        self.code_tab.pack(fill="both", expand=True)

        self.instructions_tab = InstructionsTabCTk(tab_instr)
        self.instructions_tab.pack(fill="both", expand=True)

        self.methods_tab = MethodsTab(tab_methods)
        self.methods_tab.pack(fill="both", expand=True)

        # Флаг: окно закрывается — все отложенные/фоновые операции сворачиваем
        self._closing = False

        # Хоткей из настроек подставляется в комбобокс вкладки «Код»
        try:
            self.code_tab.hotkey_combo.set(get_setting("macro_hotkey", "F8"))
        except Exception:
            pass

        # Запускаем глобальный хоткей сразу (окно модальное — F8 работает и с клавиатуры)
        self.after(200, self.register_macro_hotkeys)

        # Заголовок окна следит за текущим файлом и флагом "не сохранено"
        self._base_title = "Редактор макросов"
        self.code_tab.on_title_update = self._update_title

        # Открываем последний файл из настроек (recent_file), если он есть.
        # Диалоги приглушаем transient-связью с этим окном.
        try:
            messagebox.parent = self
        except Exception:
            pass
        try:
            self.after(150, self.code_tab.load_last_file)
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self.close_window)

    def _update_title(self):
        if self.code_tab.current_file:
            import os
            name = os.path.basename(self.code_tab.current_file)
            mark = " •" if self.code_tab.dirty else ""
            self.title(f"{self._base_title} — {name}{mark}")
        else:
            mark = " •" if self.code_tab.dirty else ""
            self.title(f"{self._base_title} — без имени{mark}")

    # ------------------------------------------------------------------
    # Глобальные хоткеи макроса (запуск / остановка)
    # ------------------------------------------------------------------
    @staticmethod
    def _to_hotkey_string(key):
        """Преобразует 'F8'/'A'/'SPACE'/... в формат pynput.GlobalHotKeys."""
        k = str(key).strip()
        if not k:
            return None
        special = {
            "SPACE": "<space>", "TAB": "<tab>", "ENTER": "<enter>",
            "ESC": "<esc>", "SHIFT": "<shift>", "CTRL": "<ctrl>",
            "ALT": "<alt>", "WIN": "<cmd>", "CMD": "<cmd>",
        }
        ku = k.upper()
        if ku in special:
            return special[ku]
        if len(k) == 1:
            return k.lower()  # одиночные символы регистронезависимы в GlobalHotKeys
        return f"<{ku.lower()}>"  # F1..F12 и прочие named-клавиши

    def register_macro_hotkeys(self):
        """Пересоздаёт глобальный листенер с текущими хоткеями запуска и остановки."""
        if not HAS_PYNPUT:
            return
        self.unregister_macro_hotkeys()

        start_key = self._to_hotkey_string(self.code_tab.hotkey_combo.get())
        stop_key = self._to_hotkey_string(get_setting("macro_stop_hotkey", "F9"))
        mappings = {}
        if start_key:
            mappings[start_key] = self.on_hotkey_start
        # Если запуск и остановка — одна клавиша, она работает как toggle
        if stop_key and stop_key != start_key:
            mappings[stop_key] = self.on_hotkey_stop
        elif stop_key == start_key:
            mappings.pop(stop_key, None)
        if not mappings:
            return

        try:
            self._macro_hotkeys = mappings
            self._hotkey_listener = pynput.keyboard.GlobalHotKeys(mappings)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
        except Exception as e:
            self.code_tab._log(f"Не удалось зарегистрировать хоткей: {e}")

    def unregister_macro_hotkeys(self):
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None
        self._macro_hotkeys = {}

    def on_hotkey_start(self):
        """Вызывается из потока pynput по горячей клавише запуска."""
        try:
            self.after(0, self._start_from_hotkey)
        except Exception:
            pass  # окно уже закрыто

    def _start_from_hotkey(self):
        running = bool(self.macro_thread and self.macro_thread.is_alive())
        if running:
            # повторное нажатие во время работы игнорируем 0.4 с,
            # чтобы случайный дабл-тап не останавливал макрос
            if time.time() - self.macro_started_at < 0.4:
                return
            self.stop_macro()
            return
        code = self.code_tab.code_box.get("1.0", "end-1c")
        self.run_code(code)

    def on_hotkey_stop(self):
        try:
            self.after(0, self.stop_macro)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Безопасный запуск кода макроса
    # ------------------------------------------------------------------
    def run_code(self, code):
        """Запускает код макроса; если уже что-то выполняется — отказывает."""
        if self._closing:
            return False
        if self.macro_thread and self.macro_thread.is_alive():
            self.code_tab._log("Макрос уже выполняется. Сначала остановите его (F9).")
            return False
        if not code.strip():
            self.code_tab._log("Пустой код.")
            return False
        try:
            compiled = compile(code, "<макрос>", "exec")
        except SyntaxError as e:
            self.code_tab._log(f"Синтаксис: {e}")
            return False
        except Exception as e:  # маловероятно, но compile может бросить и другое
            self.code_tab._log(f"Ошибка компиляции: {e}")
            return False

        self.macro_stop_event.clear()
        self.macro_started_at = time.time()
        # новый экземпляр функций ввода на каждый запуск (свежее состояние зажатых клавиш)
        try:
            self.code_tab._rebuild_globals()
        except Exception:
            pass

        def target():
            release_fn = None
            stopped = False
            try:
                g = dict(self.code_tab.global_funcs)
                exec(compiled, g)
                release_fn = g.get("_release_all")
            except MacroStop:
                stopped = True
            except SystemExit:
                stopped = True
            except BaseException as e:  # перехватываем и KeyboardInterrupt-подобные случаи
                if not self.macro_stop_event.is_set():
                    self.code_tab._print_safe(f"Ошибка: {e}")
                    try:
                        last = traceback.format_exc().strip().splitlines()[-1]
                    except Exception:
                        last = str(e)
                    self.code_tab._log(last)
            finally:
                # гарантированно отпускаем зажатые клавиши/кнопки мыши
                if release_fn is None:
                    release_fn = getattr(self.code_tab, "macros_functions", None)
                    release_fn = getattr(release_fn, "release_all", None) if release_fn else None
                if release_fn is not None:
                    try:
                        release_fn()
                    except Exception:
                        pass
                self._release_fn = None
                self.macro_thread = None
                done = stopped or self.macro_stop_event.is_set()
                self.code_tab._print_safe("Остановлено." if done else "Завершено.")

        try:
            self.macro_thread = threading.Thread(target=target, daemon=True)
            self.macro_thread.start()
        except Exception as e:  # например, не удалось создать поток
            self.macro_thread = None
            self.code_tab._log(f"Не удалось запустить макрос: {e}")
            return False
        # ссылка на release текущего экземпляра функций — для мгновенной остановки
        self._release_fn = self.code_tab.global_funcs.get("_release_all")
        self.code_tab._log("Запущено.")
        return True

    def stop_macro(self):
        """Останавливает макрос: флаг + принудительное отпускание ввода."""
        if not (self.macro_thread and self.macro_thread.is_alive()):
            self.code_tab._log("Сейчас ничего не выполняется.")
            return
        self.macro_stop_event.set()
        if self._release_fn:
            try:
                self._release_fn()
            except Exception:
                pass
        self.code_tab._log("Остановка...")
        thread = self.macro_thread
        # поток daemon, join только чтобы показать статус, UI не блокируем надолго
        threading.Thread(target=self._join_and_report, args=(thread,), daemon=True).start()

    def _join_and_report(self, thread):
        thread.join(timeout=3.0)
        if self._closing:
            return
        if thread.is_alive():
            self.code_tab._log("Поток не ответил (возможно, ждёт блокирующую операцию).")
        # следующий запуск можно разрешить сразу
        self.macro_started_at = 0.0

    # ------------------------------------------------------------------
    # Закрытие окна
    # ------------------------------------------------------------------
    def close_window(self):
        if self._closing:
            return
        # Не даём закрыть окно с несохранёнными изменениями без подтверждения
        try:
            if not self.code_tab.try_close():
                return
        except Exception:
            pass
        self._closing = True
        self.macro_stop_event.set()
        if self._release_fn:
            try:
                self._release_fn()
            except Exception:
                pass
        self.unregister_macro_hotkeys()
        try:
            messagebox.parent = None
        except Exception:
            pass
        try:
            self.parent.deiconify()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass