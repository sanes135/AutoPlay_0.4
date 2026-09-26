import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import re
import threading, time, traceback, os

from config.settings import (
    get_registry_value, set_registry_value, add_recent_file, get_recent_files,
)
from core.macros_functions import MacrosFunctions
from utils.macro_files import (
    FILE_TYPES, ensure_extension, read_macro_file, write_macro_file,
)
from ui.code_editor import CodeEditorFrame


class MacroStop(Exception):
    """Бросается внутри макроса при остановке по хоткею/кнопке."""
    pass


class CodeTabCTk(ctk.CTkFrame):
    def __init__(self, master, macro_window=None):
        super().__init__(master)
        self.macro_window = macro_window  # MacroEditorWindow (запуск/хоткеи) или None
        self.stop_event = threading.Event()
        if macro_window is not None:
            # единый флаг остановки с окном — хоткей и кнопка работают согласованно
            self.stop_event = macro_window.macro_stop_event
        self.thread = None

        # Текущий файл макроса и признак несохранённых изменений
        self.current_file = None
        self.dirty = False
        # Колбэк для обновления заголовка окна (устанавливает MacroEditorWindow)
        self.on_title_update = None

        self._build_ui()
        self._setup_globals()
        if macro_window is not None:
            # единый флаг остановки с окном — хоткей и кнопка работают согласованно
            self.stop_event = macro_window.macro_stop_event
            self._rebuild_globals()
        self._bind_events()
        self.recent_combo.bind("<<ComboboxSelected>>", lambda e: self.open_recent_from_combo())

        # Смена хоткея в комбоксе -> перерегистрация глобального листенера + сохранение
        self.hotkey_combo.bind("<<ComboboxSelected>>", lambda e: self._on_hotkey_changed())
        self.hotkey_combo.bind("<Return>", lambda e: self._on_hotkey_changed())
        self.hotkey_combo.bind("<FocusOut>", lambda e: self._on_hotkey_changed())

        # Тема редактора следует за темой приложения (Dark/Light/System)
        try:
            mode = ctk.get_appearance_mode()
            if str(mode).lower() == "system":
                mode = "Dark" if tk.Misc.winfo_rgb(self.cget("fg_color"))[0] < 32768 else "Light"
        except Exception:
            mode = "Dark"
        self.editor_frame.set_theme(str(mode))

        # Редактор без файла по умолчанию — создаём новый
        self.new_file(force=True)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Левая часть: редактор
        # Левая часть: редактор кода с IDE-функциями (подсветка, автоотступы,
        # автопарные скобки/кавычки, номера строк и т.д.)
        self.editor_frame = CodeEditorFrame(self, font_size=get_registry_value("font_size", 12))
        self.code_box = self.editor_frame.text
        # T9-подсказки: функции макросов + уже набранные в коде слова
        try:
            self.code_box.set_completion_source(self._completion_words)
        except Exception:
            pass
        self.editor_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Правая часть: консоль
        self.console = ctk.CTkTextbox(self, wrap="word", state="disabled")
        self.console.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        # Кнопки
        btn_frame = ctk.CTkFrame(self)
        btn_frame.grid(row=1, column=0, columnspan=2, pady=5, padx=5, sticky="ew")
        ctk.CTkButton(btn_frame, text="Новый", command=self.new_file).pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="Открыть", command=self.open_file_dialog).pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkLabel(btn_frame, text="Последние:").pack(side="left", padx=(10, 2))
        self.recent_combo = ctk.CTkComboBox(btn_frame, values=self._recent_values(), width=220)
        self.recent_combo.pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="Сохранить", command=self.save_cur_file).pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="Сохранить как", command=self.save_new_file).pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="Загрузить", command=self.load).pack(side="left", padx=5, expand=True, fill="x")

        # Индикатор текущего файла
        self.file_label = ctk.CTkLabel(self, text="", anchor="w")
        self.file_label.grid(row=4, column=0, columnspan=2, padx=8, sticky="ew")

        # Панель поиска по коду (Ctrl+F)
        self.find_frame = ctk.CTkFrame(self)
        self.find_entry = ctk.CTkEntry(self.find_frame, width=180, placeholder_text="Найти в коде...")
        self.find_entry.pack(side="left", padx=5, pady=3)
        ctk.CTkButton(self.find_frame, text="Найти", width=60,
                      command=lambda: self._do_find(False)).pack(side="left", padx=2)
        ctk.CTkButton(self.find_frame, text="Назад", width=60,
                      command=lambda: self._do_find(True)).pack(side="left", padx=2)
        self.find_info = ctk.CTkLabel(self.find_frame, text="")
        self.find_info.pack(side="left", padx=5)
        ctk.CTkButton(self.find_frame, text="✕", width=30,
                      command=self._hide_search).pack(side="right", padx=5)
        self.find_entry.bind("<Return>", lambda e: self._do_find(False))
        self.find_entry.bind("<KP_Enter>", lambda e: self._do_find(False))
        self.find_entry.bind("<Shift-Return>", lambda e: self._do_find(True))
        self.find_entry.bind("<Escape>", lambda e: self._hide_search())

        # Хоткей и загрузка
        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=2, column=0, pady=5, columnspan=2, padx=5, sticky="ew")
        ctk.CTkLabel(top_frame, text="Хоткей:").pack(side="left", padx=5)
        self.hotkey_combo = ctk.CTkComboBox(top_frame, values=(
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
            "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S",
            "T", "U", "V", "W", "X", "Y", "Z",
            "ALT", "CTRL", "TAB", "SHIFT", "SPACE",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"
        ))
        self.hotkey_combo.pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(top_frame, text="Запустить", command=self.start).pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkButton(top_frame, text="Выключить", command=self.stop).pack(side="left", padx=5, expand=True, fill="x")


    def _setup_globals(self):
        """Окружение для кода макроса: все функции MacrosFunctions + сервисные.

        Экземпляр MacrosFunctions создаётся один раз и переиспользуется:
        конструктор контроллера pynput достаточно тяжёл, а состояние
        зажатых клавиш очищается через release_all() при остановке.
        """
        stop_event = self.stop_event

        def check_stop():
            """Прерывает макрос, если нажата остановка (можно вызывать в циклах)."""
            if stop_event.is_set():
                raise MacroStop("Остановлено пользователем")

        def interruptible_sleep(seconds):
            """time.sleep, который мгновенно реагирует на остановку макроса."""
            try:
                seconds = float(seconds)
            except (TypeError, ValueError):
                seconds = 0.0
            end = time.time() + max(0.0, seconds)
            while True:
                check_stop()
                remaining = end - time.time()
                if remaining <= 0:
                    return
                time.sleep(min(0.05, remaining))

        mf = getattr(self, "macros_functions", None)
        if mf is None:
            try:
                mf = MacrosFunctions()
            except Exception as e:  # pynput недоступен — макрос не заработает, но UI жив
                self._log(f"Не удалось инициализировать ввод: {e}")
                mf = None
            self.macros_functions = mf

        g = {
            "print": self._print_safe,
            "wait": interruptible_sleep,
            "sleep": interruptible_sleep,   # безопасная замена time.sleep внутри макроса
            "should_stop": stop_event.is_set,
            "check_stop": check_stop,
            "_release_all": mf.release_all if mf else (lambda: None),
        }
        # Все публичные методы MacrosFunctions доступны по своим именам:
        # key_press, key_release, key_tap, write, mouse_click, mouse_press,
        # mouse_release, mouse_move, mouse_drag, mouse_position, mouse_scroll...
        if mf is not None:
            for name in dir(MacrosFunctions):
                if name.startswith("_"):
                    continue
                try:
                    attr = getattr(mf, name)
                except Exception:
                    continue
                if callable(attr):
                    g[name] = attr
        self.global_funcs = g

    def _rebuild_globals(self):
        """Синхронизировать окружение с флагом остановки окна (вызывается перед запуском)."""
        self._setup_globals()
        # stop_event должен остаться тем же объектом, что использует окно
        if self.macro_window is not None:
            self.stop_event = self.macro_window.macro_stop_event
            self.global_funcs["should_stop"] = self.stop_event.is_set
            stop_event = self.stop_event

            def check_stop():
                if stop_event.is_set():
                    raise MacroStop("Остановлено пользователем")
            self.global_funcs["check_stop"] = check_stop
            if self.macros_functions is not None:
                self.global_funcs["_release_all"] = self.macros_functions.release_all

    def _bind_events(self):
        # Отслеживаем правки текста для флага "не сохранено"
        self.code_box.bind("<<Modified>>", self._on_text_modified)
        # Хоткеи редактора: Ctrl+S / Ctrl+O / Ctrl+N / Ctrl+F (customtkinter
        # запрещает bind_all, поэтому вешаем на tk-виджеты и toplevel окна)
        widgets = [self.code_box]
        toplevel = self.winfo_toplevel()
        if hasattr(toplevel, "_textbox"):
            widgets.append(toplevel._textbox)
        for w in widgets:
            w.bind("<Control-s>", lambda e: self.save_cur_file())
            w.bind("<Control-S>", lambda e: self.save_cur_file())
            w.bind("<Control-o>", lambda e: self.open_file_dialog())
            w.bind("<Control-O>", lambda e: self.open_file_dialog())
            w.bind("<Control-n>", lambda e: self.new_file())
            w.bind("<Control-N>", lambda e: self.new_file())
            w.bind("<Control-f>", lambda e: self._show_search())
            w.bind("<Control-F>", lambda e: self._show_search())

    # ---------- T9-подсказки (автодополнение) ----------

    _SNIPPETS = {
        "click": 'mouse_click("left")',
        "rclick": 'mouse_click("right")',
        "tap": 'key_tap("enter")',
        "write": 'write("текст", interval=0.02)',
        "move": "mouse_move(0, 0, absolute=True)",
        "drag": "mouse_drag(0, 0, 100, 100, duration=0.5)",
        "scroll": "mouse_scroll(0, -3)",
        "hold": 'key_press("shift")\nwait(1)\nkey_release("shift")',
        "loop": "while not should_stop():\n    mouse_click()\n    wait(1)",
        "sleep": "wait(1)",
    }

    def _completion_words(self, prefix, line_prefix=""):
        """Варианты автодополнения: функции макроса, сниппеты и слова из кода."""
        words = set()
        try:
            words.update(k for k in self.global_funcs if not k.startswith("_"))
        except Exception:
            pass
        try:
            import builtins
            words.update(n for n in dir(builtins) if n[0].islower())
        except Exception:
            pass
        # слова, уже встречающиеся в коде пользователя
        try:
            text = self.code_box.get("1.0", "end-1c")
            words.update(re.findall(r"[A-Za-z_][A-Za-z_0-9]{1,}", text))
        except Exception:
            pass
        result = [w for w in words if w.lower().startswith(prefix.lower())]
        # сниппеты подставляем целиком (например click -> mouse_click("left"))
        for name, snippet in self._SNIPPETS.items():
            if name.startswith(prefix.lower()):
                result.append(snippet)
        return result

    # ---------- Хоткей запуска макроса ----------

    def _on_hotkey_changed(self):
        """Сохраняет выбранный хоткей в настройки и перерегистрирует листенер."""
        key = self.hotkey_combo.get().strip()
        if not key:
            return
        self.hotkey_combo.set(key)
        try:
            from config.settings import set_setting
            set_setting("macro_hotkey", key)
        except Exception:
            pass
        if self.macro_window is not None:
            try:
                self.macro_window.register_macro_hotkeys()
            except Exception:
                pass

    # ---------- Поиск по коду ----------

    def _show_search(self):
        # панель появляется поверх редактора, справа сверху
        self.find_frame.grid(row=0, column=0, sticky="ne", padx=10, pady=8)
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")

    def _hide_search(self, event=None):
        self.find_frame.grid_forget()
        self.code_box.tag_remove("found", "1.0", "end")
        self.find_info.configure(text="")
        self.code_box.focus_set()

    def _do_find(self, backwards=False):
        pattern = self.find_entry.get()
        if not pattern:
            self.find_info.configure(text="")
            return
        found = self.code_box.find_next(pattern, backwards=backwards)
        self.find_info.configure(text="✓ найдено" if found else "✕ не найдено")

    def _on_text_modified(self, event=None):
        if self.code_box.edit_modified():
            self._set_dirty(True)
            self.code_box.edit_modified(False)

    def _set_dirty(self, dirty):
        self.dirty = dirty
        self._update_file_label()
        if callable(self.on_title_update):
            try:
                self.on_title_update()
            except Exception:
                pass

    # ---------- Работа с файлами ----------

    def _recent_values(self):
        files = get_recent_files()
        return files if files else ["— нет —"]

    def _refresh_recent(self):
        self.recent_combo.configure(values=self._recent_values())

    def _update_file_label(self):
        if self.current_file:
            name = os.path.basename(self.current_file)
            mark = " •" if self.dirty else ""
            text = f"Файл: {name}{mark}"
        else:
            text = "Файл: без имени (новый)" + (" •" if self.dirty else "")
        self.file_label.configure(text=text)

    def new_file(self, force=False):
        """Очищает редактор и начинает новый файл (с подтверждением при правках)."""
        if not force and not self._confirm_discard():
            return False
        self._set_text("")
        self.current_file = None
        self._set_dirty(False)
        return True

    def open_file_dialog(self):
        """Показывает диалог выбора файла и открывает его."""
        if not self._confirm_discard():
            return False
        path = filedialog.askopenfilename(
            title="Открыть макрос",
            filetypes=FILE_TYPES,
        )
        if path:
            return self.open_file(path)
        return False

    def open_recent_from_combo(self):
        """Открывает файл, выбранный в выпадающем списке последних файлов."""
        value = self.recent_combo.get()
        if value and value != "— нет —" and os.path.isfile(value):
            self.open_file(value)

    def open_file(self, path):
        """Читает файл макроса в редактор и запоминает его как текущий."""
        path = os.path.abspath(path)
        try:
            content = read_macro_file(path)
        except Exception as e:
            messagebox.showerror("Ошибка открытия", f"Не удалось открыть файл:\n{path}\n\n{e}")
            self._log(f"Ошибка открытия файла: {e}")
            return False
        self._set_text(content)
        self.current_file = path
        self._set_dirty(False)
        add_recent_file(path)
        self._refresh_recent()
        # Запоминаем последний открытый файл в настройках
        set_registry_value("last_opened_file", path)
        self._log(f"Открыт файл: {path}")
        return True

    def save_cur_file(self):
        """Сохраняет в текущий файл; если файла нет — открывает «Сохранить как»."""
        if not self.current_file:
            return self.save_new_file()
        return self._write_to_file(self.current_file)

    def save_new_file(self):
        """Сохранение в новый файл через диалог «Сохранить как»."""
        initial = os.path.basename(self.current_file) if self.current_file else "untitled.macro"
        path = filedialog.asksaveasfilename(
            title="Сохранить макрос как",
            defaultextension=".macro",
            initialfile=initial,
            filetypes=FILE_TYPES,
        )
        if not path:
            return False
        path = ensure_extension(os.path.abspath(path))
        if self._write_to_file(path):
            self.current_file = path
            add_recent_file(path)
            self._refresh_recent()
            return True
        return False

    def _write_to_file(self, path):
        try:
            code = self.code_box.get("1.0", "end-1c")
        except Exception as e:
            self._log(f"Не удалось прочитать редактор: {e}")
            return False
        try:
            write_macro_file(path, code)
        except Exception as e:
            try:
                messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить файл:\n{path}\n\n{e}")
            except Exception:
                pass
            self._log(f"Ошибка сохранения: {e}")
            return False
        self._set_dirty(False)
        self._log(f"Сохранено: {path}")
        return True

    def load(self):
        """Совместимая кнопка: открывает диалог загрузки файла."""
        return self.open_file_dialog()

    def try_close(self):
        """Проверяет несохранённые изменения перед закрытием вкладки/окна."""
        try:
            file_text = ''.join(open(self.current_file, 'r', encoding='utf-8').readlines())
        except:
            file_text = None
        if not self.code_box.get("1.0", "end-1c") == file_text:
            return self._confirm_discard()
        else:
            return True

    def _confirm_discard(self):
        """True, если можно переходить к другому файлу (нет правок или пользователь согласился)."""
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Несохранённые изменения",
            "Есть несохранённые изменения. Сохранить перед продолжением?",
        )
        if answer is None:  # Отмена — прерываем операцию
            return False
        if answer:  # Да — сохраняем и продолжаем, если сохранилось
            return bool(self.save_cur_file())
        return True  # Нет — выходим без сохранения

    def _set_text(self, text):
        self.code_box.delete("1.0", "end")
        if text:
            self.code_box.insert("1.0", text)
        # programmatic-правка не должна помечать документ как несохранённый:
        # сбрасываем dirty сразу после загрузки (флаг Modified сбрасывает сам редактор)
        self._set_dirty(False)

    def load_last_file(self):
        """Загружает последний открытый файл (из recent_file), если он есть."""
        files = get_recent_files()
        if files and self.open_file(files[0]):
            return True
        return False

    def start(self):
        """Кнопка «Запустить»: делегирует окну-редактору (единая точка запуска)."""
        code = self.code_box.get("1.0", "end-1c")
        if self.macro_window is not None:
            return self.macro_window.run_code(code)
        # фолбэк, если вставка используется без окна (старое поведение, но безопасно)
        if self.thread and self.thread.is_alive():
            return self._log("Уже выполняется.")
        self.stop_event.clear()
        if not code.strip():
            return self._log("Пустой код.")
        try:
            compiled = compile(code, "<macro>", "exec")
        except SyntaxError as e:
            return self._log(f"Синтаксис: {e}")
        except Exception as e:
            return self._log(f"Ошибка компиляции: {e}")
        self._rebuild_globals()
        try:
            self.thread = threading.Thread(target=self._run, args=(compiled,), daemon=True)
            self.thread.start()
        except Exception as e:
            self.thread = None
            return self._log(f"Не удалось запустить: {e}")
        self._log("Запущено.")

    def _run(self, compiled):
        try:
            exec(compiled, self.global_funcs)
        except MacroStop:
            pass
        except SystemExit:
            pass
        except BaseException as e:
            if not self.stop_event.is_set():
                self._print_safe(f"Ошибка: {e}")
                try:
                    last = traceback.format_exc().strip().splitlines()[-1]
                except Exception:
                    last = str(e)
                self._log(last)
        finally:
            try:
                self.macros_functions.release_all()
            except Exception:
                pass
            self.thread = None
            self._print_safe("Остановлено." if self.stop_event.is_set() else "Завершено.")

    def stop(self):
        """Кнопка «Выключить»: корректная остановка через окно/флаг."""
        if self.macro_window is not None:
            return self.macro_window.stop_macro()
        if not (self.thread and self.thread.is_alive()):
            return self._log("Сейчас ничего не выполняется.")
        self.stop_event.set()
        try:
            self.macros_functions.release_all()
        except Exception:
            pass
        self._log("Остановка...")

    def _wait_safe(self, sec):
        end = time.time() + sec
        while time.time() < end and not self.stop_event.is_set():
            time.sleep(0.01)

    def _print_safe(self, *args):
        """Безопасный вывод из рабочих потоков: в UI — только через after()."""
        msg = " ".join(map(str, args))
        try:
            self.after(0, lambda: self._log(msg))
        except Exception:
            pass  # виджет уже уничтожен

    def _log(self, text):
        """Лог в консоль с троттлингом и ограничением длины истории."""
        # защита от вызова из чужого потока (Tk работает только из потока создания)
        try:
            import threading as _th
            if _th.current_thread() is not _th.main_thread():
                self.after(0, lambda t=str(text): self._log(t))
                return
        except Exception:
            pass

        self._write_log_line(str(text))

    def _write_log_line(self, line):
        try:
            self.console.configure(state="normal")
            self.console.insert("end", line + "\n")
            # ограничение истории консоли — не даём разрастаться при спаме
            lines = int(self.console.index("end-1c").split(".")[0])
            if lines > 1000:
                self.console.delete("1.0", f"{lines - 800}.0")
            self.console.see("end")
            self.console.configure(state="disabled")
        except Exception:
            pass  # консоль уничтожена — молча игнорируем