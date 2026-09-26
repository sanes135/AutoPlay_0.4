"""
Редактор кода макросов в стиле современных IDE:
- подсветка синтаксиса Python (Pygments, с фолбэком на regex);
- автоотступы и автоматическая расстановка скобок/кавычек;
- Tab — отступ выделенных строк (Shift+Tab — обратный сдвиг);
- Ctrl+D — дублировать строку, Ctrl+/ — комментировать блок,
  Alt+стрелки — переместить строку, Ctrl+Enter — пустая строка ниже;
- нумерация строк (gutter), подсветка текущей строки;
- поиск F3 / Shift+F3.
"""

import re
import tkinter as tk
import tkinter.font as tkfont


# ----------------------------------------------------------------------
# T9-подобное автодополнение (как в современных IDE)
# ----------------------------------------------------------------------
class _CompletionPopup:
    """Всплывающий список вариантов над редактором.

    completion — callable(prefix, line_prefix) -> list[str], возвращает
    возможные завершения для слова, напечатанного перед курсором.
    Управление: Tab/Enter — принять, стрелки — выбор, Esc — закрыть.
    """

    def __init__(self, text_widget, completion):
        self.text = text_widget
        self.completion = completion
        self.toplevel = None
        self.listbox = None
        self.items = []
        self.prefix_start = None  # индекс начала слова в тексте

    # ---- публичное API ----
    def is_visible(self):
        return self.toplevel is not None and self.toplevel.winfo_exists()

    def show(self):
        """Показать варианты для слова под курсором; False — показывать нечего."""
        cursor = self.text.index("insert")
        line_prefix = self.text.get(f"{cursor} linestart", cursor)
        m = re.search(r"[A-Za-z_А-Яа-яЁё0-9_]*$", line_prefix)
        prefix = m.group(0) if m else ""
        if len(prefix) < 2:
            self.hide()
            return False
        try:
            items = sorted(set(self.completion(prefix, line_prefix)))
        except Exception:
            items = []
        items = [i for i in items if i.lower().startswith(prefix.lower()) and i != prefix]
        if not items:
            self.hide()
            return False
        self.items = items[:12]
        self.prefix_start = f"{cursor} - {len(prefix)} c"
        self._create_window(cursor)
        return True

    def hide(self):
        if self.toplevel is not None:
            try:
                self.toplevel.destroy()
            except Exception:
                pass
            self.toplevel = None
            self.listbox = None

    def accept(self):
        """Подставляет выбранный вариант. True, если что-то подставлено."""
        if not self.is_visible():
            return False
        sel = self.listbox.curselection()
        word = self.items[sel[0]] if sel else (self.items[0] if self.items else None)
        self.hide()
        if word is None:
            return False
        cursor = self.text.index("insert")
        end = f"{cursor} wordend"
        if self.text.compare(end, "<", cursor):
            end = cursor
        self.text._silent_edit(lambda: self.text.replace(self.prefix_start, end, word))
        return True

    # ---- обработка клавиш (возвращает "break", если клавиша перехвачена) ----
    def handle_key(self, event):
        if not self.is_visible():
            return None
        keysym = event.keysym
        if keysym in ("Escape",):
            self.hide()
            return "break"
        if keysym in ("Down",):
            nxt = min(self.listbox.size() - 1,
                      (self.listbox.curselection() or (-1,))[0] + 1)
            self.listbox.selection_set(nxt)
            self.listbox.see(nxt)
            return "break"
        if keysym in ("Up",):
            prv = max(0, (self.listbox.curselection() or (0,))[0] - 1)
            self.listbox.selection_set(prv)
            self.listbox.see(prv)
            return "break"
        if keysym in ("Return", "KP_Enter"):
            self.accept()
            return "break"
        if keysym == "Tab":
            # Tab принимает вариант вместо отступа
            self.accept()
            return "break"
        return None

    # ---- внутреннее ----
    def _create_window(self, cursor):
        self.hide()
        try:
            x = self.text.bbox(cursor)
            if x is None:
                return
            bx, by, bh, _ = x
            anchor = self.text.winfo_rootx() + bx
            yroot = self.text.winfo_rooty() + by
        except tk.TclError:
            return
        top = tk.Toplevel(self.text)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        font = self.text.cget("font")
        try:
            f = tkfont.Font(font=font)
            width = max(len(w) for w in self.items) * f.measure("0") + 24
            height_each = f.linespace() + 4
        except Exception:
            width, height_each = 200, 18
        h = height_each * len(self.items) + 4
        top.geometry(f"{max(120, int(width))}x{int(h)}+{int(anchor)}+{int(yroot - h - 2)}")

        lb = tk.Listbox(top, exportselection=False, activestyle="none",
                        relief="solid", bd=1, highlightthickness=0, font=font)
        try:
            colors = self.text._colors
            lb.configure(bg=colors["bg"], fg=colors["fg"],
                         selectbackground=colors["active_bg"], selectforeground=colors["fg"])
        except Exception:
            pass
        for item in self.items:
            lb.insert("end", " " + item)
        lb.selection_set(0)
        lb.pack(fill="both", expand=True)
        lb.bind("<ButtonRelease-1>", lambda e: self.accept())

        self.toplevel = top
        self.listbox = lb

try:
    from pygments import lexers
    from pygments.util import ClassNotFound
    _HAVE_PYGMENTS = True
except ImportError:
    _HAVE_PYGMENTS = False

# Цвета тем (совместимы с dark/light режимами customtkinter)
DARK_COLORS = {
    "bg": "#1e1e1e",
    "fg": "#d4d4d4",
    "gutter_bg": "#252526",
    "gutter_fg": "#858585",
    "gutter_current_fg": "#c6c6c6",
    "active_bg": "#2a2d2e",
    "keyword": "#569cd6",
    "string": "#ce9178",
    "comment": "#6a9955",
    "number": "#b5cea8",
    "function": "#dcdcaa",
    "classname": "#4ec9b0",
    "builtin": "#4fc1ff",
    "operator": "#d4d4d4",
    "punctuation": "#ffd700",
    "decorator": "#d7ba7d",
}

LIGHT_COLORS = {
    "bg": "#ffffff",
    "fg": "#1e1e1e",
    "gutter_bg": "#f3f3f3",
    "gutter_fg": "#9e9e9e",
    "gutter_current_fg": "#1e1e1e",
    "active_bg": "#e8f0fe",
    "keyword": "#0000ff",
    "string": "#a31515",
    "comment": "#008000",
    "number": "#098658",
    "function": "#795e26",
    "classname": "#267f99",
    "builtin": "#0000ff",
    "operator": "#000000",
    "punctuation": "#7f7f7f",
    "decorator": "#0451a5",
}

INDENT = "    "  # 4 пробела, как в PEP8

_CLOSERS = set(")]}\"'")
_PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}

_HL_TAGS = ("keyword", "string", "comment", "number", "function",
            "classname", "builtin", "operator", "punctuation", "decorator")


def _regex_tokenize(line):
    """Запасной токенизатор, если Pygments недоступен.
    Возвращает список (tag, start, end) для одной строки."""
    patterns = [
        ("comment", r"#.*$"),
        ("string", r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''),
        ("keyword", r"\b(def|class|if|elif|else|while|for|in|return|import|from|as|pass|break|"
                    r"continue|and|or|not|is|None|True|False|try|except|finally|with|lambda|yield|"
                    r"global|nonlocal|assert|raise|del|async|await)\b"),
        ("builtin", r"\b(print|wait|should_stop|range|int|str|float|list|dict|set|tuple|bool|len|"
                    r"abs|min|max|sum|round|enumerate|zip|input|type|isinstance|open|time|random)\b"),
        ("decorator", r"@[\w.]+"),
        ("number", r"\b\d+(?:\.\d+)?\b"),
    ]
    spans = []
    taken = []
    for tag, pat in patterns:
        for m in re.finditer(pat, line):
            s, e = m.span()
            if any(not (e <= ts or s >= te) for ts, te in taken):
                continue
            taken.append((s, e))
            spans.append((tag, s, e))
    return spans


if _HAVE_PYGMENTS:

    def _map_pygment_token(tok):
        t = str(tok)
        if t.startswith("Token.Keyword"):
            return "keyword"
        if t.startswith("Token.Name.Function"):
            return "function"
        if t.startswith("Token.Name.Class"):
            return "classname"
        if t.startswith("Token.Name.Decorator"):
            return "decorator"
        if t.startswith("Token.Name.Builtin"):
            return "builtin"
        if t.startswith("Token.Literal.String"):
            return "string"
        if t.startswith("Token.Literal.Number"):
            return "number"
        if t.startswith("Token.Comment"):
            return "comment"
        if t.startswith("Token.Operator"):
            return "operator"
        if t.startswith("Token.Punctuation"):
            return "punctuation"
        return None

    try:
        _LEXER = lexers.get_lexer_by_name("python")
    except ClassNotFound:
        _LEXER = None
else:
    _LEXER = None


class CodeEditorFrame(tk.Frame):
    """Рамка редактора кода: слева номера строк (gutter), справа текстовый
    виджет с IDE-функциями. Доступ к тексту — через self.text."""

    def __init__(self, master, font_size=12, completion=None, **kwargs):
        super().__init__(master, **kwargs)
        self.text = _CodeText(self, font_size=font_size, completion=completion)
        self.gutter = self.text.gutter
        self.text.pack(side="right", fill="both", expand=True)

    # проксируем часто используемые методы на текстовый виджет
    def get(self, *args, **kw):
        return self.text.get(*args, **kw)

    def insert(self, *args, **kw):
        return self.text.insert(*args, **kw)

    def delete(self, *args, **kw):
        return self.text.delete(*args, **kw)

    def set_theme(self, appearance):
        self.text.set_theme(appearance)

    def set_font_size(self, size):
        self.text.set_font_size(size)


class _CodeText(tk.Text):
    """tk.Text с подсветкой синтаксиса, автоотступами, парными скобками,
    номерами строк и прочими IDE-мелочами."""

    _last_search = ""

    def __init__(self, master, font_size=12, completion=None, **kwargs):
        kwargs.setdefault("wrap", "none")
        kwargs.setdefault("undo", True)
        kwargs.setdefault("padx", 4)
        kwargs.setdefault("borderwidth", 0)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("insertwidth", 2)
        kwargs.setdefault("spacing1", 1)
        kwargs.setdefault("spacing3", 1)
        super().__init__(master, **kwargs)

        self._font_size = max(8, min(28, int(font_size)))
        self._theme_name = "dark"
        self._colors = dict(DARK_COLORS)
        self._highlight_job = None
        self._updating_gutter = False
        self._in_silent_edit = False

        # T9-подобное автодополнение (источник вариантов задаёт владелец редактора)
        self.completion_popup = _CompletionPopup(self, completion or (lambda p: []))
        self._comp_job = None

        self._setup_font()
        self.gutter = tk.Canvas(master, width=48, highlightthickness=0, bd=0,
                                background=self._colors["gutter_bg"])
        self.gutter.bind("<Button-1>", lambda e: "break")
        self.gutter.pack(side="left", fill="y")
        self._setup_tags()
        self._bind_keys()
        self._apply_theme_colors()

        # синхронизация вертикальной прокрутки gutter со скроллом текста
        self.bind("<MouseWheel>", lambda e: self.after_idle(self._redraw_gutter), add="+")
        self.bind("<Button-4>", lambda e: self.after_idle(self._redraw_gutter), add="+")
        self.bind("<Button-5>", lambda e: self.after_idle(self._redraw_gutter), add="+")
        self.bind("<KeyRelease>", self._on_keyrelease, add="+")
        self.bind("<ButtonRelease-1>", self._on_click, add="+")
        self.bind("<<Modified>>", self._on_modified, add="+")
        self.bind("<Configure>", lambda e: self.after_idle(self._refresh_all), add="+")
        self.bind("<<Paste>>", lambda e: self.after_idle(self._refresh_all), add="+")
        self.bind("<<Undo>>", lambda e: self.after_idle(self._refresh_all), add="+")
        self.bind("<<Redo>>", lambda e: self.after_idle(self._refresh_all), add="+")

    # ---------- Инициализация ----------

    def _setup_font(self):
        family = "Consolas"
        try:
            available = set(tkfont.families())
            for cand in ("Cascadia Mono", "JetBrains Mono", "Fira Code", "Source Code Pro",
                         "Menlo", "DejaVu Sans Mono", "Courier New"):
                if cand in available:
                    family = cand
                    break
        except Exception:
            pass
        self._font_family = family
        self._gutter_font = (family, self._font_size)
        self.configure(font=(family, self._font_size))

    def _setup_tags(self):
        self.tag_configure("current_line", background=self._colors["active_bg"])
        self.tag_lower("current_line")
        for name in _HL_TAGS:
            self.tag_configure(name, foreground=self._colors[name])
        self.tag_configure("found", background="#515c6a")

    def _bind_keys(self):
        b = self.bind
        keysyms = {"(": "parenleft", ")": "parenright", "[": "bracketleft",
                   "]": "bracketright", "{": "braceleft", "}": "braceright",
                   '"': "quotedbl", "'": "apostrophe"}
        b("<Return>", self._on_return)
        b("<KP_Enter>", self._on_return)
        b("<Control-Return>", self._on_ctrl_return)
        b("<Tab>", self._on_tab)
        b("<Shift-ISO_Left_Tab>", self._on_shift_tab)
        b("<Shift-Tab>", self._on_shift_tab)
        b("<BackSpace>", self._on_backspace)
        b("<Control-d>", self._duplicate_line)
        b("<Control-D>", self._duplicate_line)
        b("<Control-slash>", self._toggle_comment)
        b("<Alt-Up>", self._move_line_up)
        b("<Alt-Down>", self._move_line_down)
        b("<Escape>", self._clear_search_tags)
        b("<Control-space>", self.trigger_completion)
        b("<F3>", lambda e: self.find_next(self._last_search) if self._last_search else None)
        b("<Shift-F3>", lambda e: self.find_next(self._last_search, backwards=True)
           if self._last_search else None)
        # автозакрытие скобок (для кавычек — отдельная логика ниже)
        for opener, closer in (("(", ")"), ("[", "]"), ("{", "}")):
            b(f"<KeyPress-{keysyms[opener]}>",
              lambda e, o=opener, c=closer: self._smart_open(o, c))
            b(f"<KeyPress-{keysyms[closer]}>",
              lambda e, ch=closer: self._smart_close(ch))
        for q in ('"', "'"):
            b(f"<KeyPress-{keysyms[q]}>", lambda e, ch=q: self._smart_quote(ch))

    # ---------- Тема / шрифт ----------

    def set_theme(self, appearance):
        """appearance: 'Dark' | 'Light' | 'System' (цвет подбирается по теме)."""
        theme = "light" if str(appearance).lower().startswith("light") else "dark"
        if theme == self._theme_name:
            return
        self._theme_name = theme
        self._colors = dict(LIGHT_COLORS if theme == "light" else DARK_COLORS)
        self._apply_theme_colors()
        self._refresh_all()

    def set_font_size(self, size):
        try:
            size = max(8, min(28, int(size)))
        except (TypeError, ValueError):
            return
        if size == self._font_size:
            return
        self._font_size = size
        self._gutter_font = (self._font_family, size)
        self.configure(font=(self._font_family, size))
        self._redraw_gutter()

    def _apply_theme_colors(self):
        self.configure(background=self._colors["bg"],
                       insertbackground=self._colors["fg"],
                       foreground=self._colors["fg"],
                       selectbackground="#264f78", selectforeground="#ffffff")
        self.gutter.configure(background=self._colors["gutter_bg"])
        self.tag_configure("current_line", background=self._colors["active_bg"])
        for name in _HL_TAGS:
            self.tag_configure(name, foreground=self._colors[name])

    # ---------- Индексы-хелперы ----------

    def _line_no(self, index=None):
        return int(self.index(index or "insert").split(".")[0])

    def _line_text(self, n):
        return self.get(f"{n}.0", f"{n}.0 lineend")

    def _get_indent(self, n):
        line = self._line_text(n)
        return line[: len(line) - len(line.lstrip(" \t"))]

    # ---------- Enter / Tab / Backspace ----------

    def _on_return(self, event=None):
        n = self._line_no()
        col = int(self.index("insert").split(".")[1])
        indent = self._get_indent(n)
        cur = self._line_text(n)[:col]
        prev = self._line_text(n - 1) if n > 1 else ""
        # «выпрыгнуть» из блока: пустая строка внутри отступа после ":" — уменьшить его
        if not cur.strip() and indent and prev.rstrip().endswith(":") \
                and len(indent) >= len(INDENT):
            self.delete(f"{n}.0", f"{n}.0 lineend+1c")
            self.insert(f"{n}.0", "\n" + indent[:-len(INDENT)])
            self.see("insert")
            self._after_edit()
            return "break"
        extra = INDENT if cur.rstrip().endswith(":") else ""
        after = self.get("insert", "insert lineend")
        between_brackets = (cur[-1:] in "([{" and after[:1] in ")]}")
        self.insert("insert", "\n" + indent + extra)
        # Enter между ()[]{} — раздвигаем пару на две строки
        if between_brackets:
            self.insert("insert", "\n" + indent)
        self.see("insert")
        self._after_edit()
        return "break"

    def _on_ctrl_return(self, event=None):
        """Ctrl+Enter — вставить пустую строку ниже, не разрывая текущую."""
        n = self._line_no()
        self.insert(f"{n}.0 lineend", "\n")
        self.mark_set("insert", f"{n + 1}.0")
        self.see("insert")
        self._after_edit()
        return "break"

    def _on_tab(self, event=None):
        # при открытом автодополнении Tab принимает вариант
        if self.completion_popup.is_visible():
            self.completion_popup.accept()
            return "break"
        if self.tag_ranges("sel"):
            self._indent_block(True)
            return "break"
        n = self._line_no()
        col = int(self.index("insert").split(".")[1])
        before = self.get(f"{n}.0", "insert")
        if not before.strip():  # пустое начало строки — нормализуем отступ
            prev_indent = self._find_prev_indent(n)
            self.delete(f"{n}.0", f"{n}.0 + {col} c")
            self.insert(f"{n}.0", prev_indent + INDENT)
        else:
            n_sp = len(INDENT) - (col % len(INDENT)) or len(INDENT)
            self.insert("insert", " " * n_sp)
        self._after_edit()
        return "break"

    def _on_shift_tab(self, event=None):
        self._indent_block(False)
        return "break"

    def _find_prev_indent(self, n):
        for ln in range(n - 1, 0, -1):
            text = self._line_text(ln)
            if text.strip():
                return self._get_indent(ln)
        return ""

    def _selected_lines(self):
        sel = self.tag_ranges("sel")
        if not sel:
            n = self._line_no()
            return n, n
        start = int(str(sel[0]).split(".")[0])
        end = int(str(sel[1]).split(".")[0])
        if str(sel[1]).split(".")[1] == "0" and end > start:
            end -= 1
        return start, end

    def _indent_block(self, indent=True):
        first, last = self._selected_lines()
        for ln in range(first, last + 1):
            line = self._line_text(ln)
            if indent:
                if line.strip():
                    self.replace(f"{ln}.0", f"{ln}.0 lineend", INDENT + line)
            elif line.startswith(INDENT):
                self.replace(f"{ln}.0", f"{ln}.0 lineend", line[len(INDENT):])
            elif line.startswith("\t"):
                self.replace(f"{ln}.0", f"{ln}.0 lineend", line[1:])
        self._after_edit()

    def _on_backspace(self, event=None):
        pos = self.index("insert")
        before = self.get(pos + "-1c", pos)
        after = self.get(pos, pos + "+1c")
        # удалить пару целиком: |( )|
        if before in _PAIRS and _PAIRS[before] == after:
            self.delete(pos + "-1c", pos + "+1c")
            self._after_edit()
            return "break"
        # на пустой строке с отступом — шаг назад на 4 пробела
        n = self._line_no()
        col = int(pos.split(".")[1])
        line = self._line_text(n)
        if col > 0 and not line.strip():
            step = min(col, len(INDENT))
            self.delete(f"{n}.{col - step}", pos)
            self._after_edit()
            return "break"
        return None  # стандартное поведение

    # ---------- Скобки и кавычки ----------

    def _smart_open(self, opener, closer):
        sel = self.tag_ranges("sel")
        if sel:  # обернуть выделение скобками
            text = self.get(sel[0], sel[1])
            self.replace(sel[0], sel[1], opener + text + closer)
            self.tag_remove("sel", "1.0", "end")
            self.mark_set("insert", f"{sel[0]} + {len(opener) + len(text)} c")
        else:
            nxt = self.get("insert", "insert+1c")
            if not nxt.isalnum() and nxt not in _CLOSERS:
                self.insert("insert", opener + closer)
                self.mark_set("insert", "insert-1c")
            else:
                self.insert("insert", opener)
        self._after_edit()
        return "break"

    def _smart_quote(self, q):
        """Кавычка: автозакрытие + умная обработка тройных кавычек (docstring)."""
        before2 = self.get("insert-2c", "insert")
        if before2 == q * 2:  # третья кавычка — открываем/закрываем docstring
            if self.get("insert", "insert+1c") == q:
                self.mark_set("insert", "insert+1c")
            else:
                self.insert("insert", q * 3)
                self.mark_set("insert", "insert-2c")
            self._after_edit()
            return "break"
        if self.get("insert-1c", "insert") == q and self.get("insert", "insert+1c") == q:
            # курсор между двух кавычек пары — пропускаем закрывающую
            self.mark_set("insert", "insert+1c")
            self._after_edit()
            return "break"
        return self._smart_open(q, q)

    def _smart_close(self, ch):
        """Пропускаем автоматически вставленную закрывающую скобку."""
        if self.get("insert", "insert+1c") == ch:
            self.mark_set("insert", "insert+1c")
            self._after_edit()
            return "break"
        self.insert("insert", ch)
        self._after_edit()
        return "break"

    # ---------- Строки: дублирование / перемещение / комментарий ----------

    def _duplicate_line(self, event=None):
        n = self._line_no()
        col = int(self.index("insert").split(".")[1])
        text = self._line_text(n)
        self.insert(f"{n}.0 lineend", "\n" + text)
        self.mark_set("insert", f"{n + 1}.{col}")
        self.see("insert")
        self._after_edit()
        return "break"

    def _move_line_up(self, event=None):
        self._swap_lines(-1)
        return "break"

    def _move_line_down(self, event=None):
        self._swap_lines(1)
        return "break"

    def _swap_lines(self, direction):
        n = self._line_no()
        m = n + direction
        total = self._line_no("end-1c")
        if m < 1 or m > total:
            return
        col = int(self.index("insert").split(".")[1])
        a, b = self._line_text(n), self._line_text(m)
        lo, hi = sorted((n, m))
        self.replace(f"{lo}.0", f"{hi}.0 lineend",
                     b + "\n" + a if direction == -1 else a + "\n" + b)
        self.mark_set("insert", f"{m}.{col}")
        self.see("insert")
        self._after_edit()

    def _toggle_comment(self, event=None):
        first, last = self._selected_lines()
        lines = [self._line_text(ln) for ln in range(first, last + 1)]
        nonempty = [l for l in lines if l.strip()]
        all_commented = bool(nonempty) and all(l.lstrip().startswith("#") for l in nonempty)
        for i, ln in enumerate(range(first, last + 1)):
            text = lines[i]
            if not text.strip():
                continue
            if all_commented:
                new = re.sub(r"^(\s*)#\s?", r"\1", text)
            else:
                indent = text[: len(text) - len(text.lstrip(" \t"))]
                new = indent + "# " + text[len(indent):]
            self.replace(f"{ln}.0", f"{ln}.0 lineend", new)
        self._after_edit()
        return "break"

    # ---------- Поиск ----------

    def find_next(self, pattern, backwards=False):
        self._last_search = pattern or self._last_search
        pattern = self._last_search
        if not pattern:
            return False
        self.tag_remove("found", "1.0", "end")
        pos = self.search(pattern, "insert", "end" if not backwards else "1.0",
                          nocase=True, backwards=backwards)
        if not pos:  # цикл: докручиваем поиск с начала/конца документа
            pos = self.search(pattern, "end-1c" if backwards else "1.0",
                              nocase=True, backwards=backwards,
                              stopindex="insert")
        if pos:
            end = f"{pos} + {len(pattern)} c"
            self.tag_add("found", pos, end)
            self.mark_set("insert", end if not backwards else pos)
            self.see("insert")
            return True
        return False

    def _clear_search_tags(self, event=None):
        self.tag_remove("found", "1.0", "end")

    # ---------- Перерисовка / подсветка ----------

    def _after_edit(self):
        self._schedule_refresh()

    # ---------- Автодополнение (T9) ----------

    def set_completion_source(self, fn):
        """fn(prefix, line_prefix) -> list[str] — источник вариантов."""
        self.completion_popup.completion = fn

    def trigger_completion(self, event=None):
        """Ctrl+Space — принудительно показать варианты."""
        self.completion_popup.show()
        return "break"

    def _maybe_show_completion(self):
        """Показывать варианты после каждого набранного слова-символа."""
        popup = self.completion_popup
        keysym = getattr(self._last_key_event, "keysym", "") if hasattr(self, "_last_key_event") else ""
        if not re.fullmatch(r"[A-Za-z_0-9]", keysym or ""):
            return
        if popup.show():
            pass  # окно показано

    def _hide_completion_on_move(self, event=None):
        # смещение курсора/скролл закрывает подсказку
        if self.completion_popup.is_visible():
            self.completion_popup.hide()

    def _silent_edit(self, action):
        """Программная правка без всплытия самой подсказки."""
        self._in_silent_edit = True
        try:
            action()
        finally:
            self.after_idle(lambda: setattr(self, "_in_silent_edit", False))

    def _on_keyrelease(self, event=None):
        self._last_key_event = event
        # перехват управления подсказкой (стрелки/Enter/Esc), если она открыта
        handled = self.completion_popup.handle_key(event)
        if handled:
            self._highlight_line()
            self._redraw_gutter()
            return handled
        self._highlight_line()
        self._redraw_gutter()
        if not self._in_silent_edit and event.keysym not in (
                "BackSpace", "Delete", "Shift_L", "Shift_R", "Control_L", "Control_R",
                "Alt_L", "Alt_R", "Up", "Down", "Left", "Right", "Return", "KP_Enter",
                "Tab", "Escape"):
            if self._comp_job is not None:
                try:
                    self.after_cancel(self._comp_job)
                except Exception:
                    pass
            self._comp_job = self.after(120, self._maybe_show_completion)

    def _on_click(self, event=None):
        self.completion_popup.hide()
        self._highlight_line()
        self._redraw_gutter()

    def _on_modified(self, event=None):
        if self.edit_modified():
            self.edit_modified(False)

    def _schedule_refresh(self):
        if self._highlight_job is not None:
            try:
                self.after_cancel(self._highlight_job)
            except Exception:
                pass
        self._highlight_job = self.after(50, self._refresh_all)

    def _refresh_all(self):
        self._highlight_job = None
        try:
            self._highlight_syntax()
            self._highlight_line()
            self._redraw_gutter()
        except tk.TclError:
            pass  # виджет уничтожен во время отложенного обновления

    def _highlight_line(self):
        self.tag_remove("current_line", "1.0", "end")
        n = self._line_no()
        self.tag_add("current_line", f"{n}.0", f"{n}.0 lineend+1c")
        self.tag_lower("current_line")

    def _highlight_syntax(self):
        total = self._line_no("end-1c")
        if total > 3000:  # на очень больших файлах подсветку пропускаем
            return
        text = self.get("1.0", "end-1c")
        for t in _HL_TAGS:
            self.tag_remove(t, "1.0", "end")
        if _LEXER is not None:
            try:
                line_starts = [0] + [m.start() + 1 for m in re.finditer("\n", text)]
                offset = 0
                for tok, value in _LEXER.get_tokens(text):
                    length = len(value)
                    tag = _map_pygment_token(tok)
                    if tag and length:
                        try:
                            s = self._offset_to_index(offset, line_starts)
                            e = self._offset_to_index(offset + length, line_starts)
                            self.tag_add(tag, s, e)
                        except tk.TclError:
                            pass
                    offset += length
                return
            except Exception:
                pass
        for ln, line in enumerate(text.split("\n"), start=1):
            for tag, s, e in _regex_tokenize(line):
                try:
                    self.tag_add(tag, f"{ln}.{s}", f"{ln}.{e}")
                except tk.TclError:
                    pass

    @staticmethod
    def _offset_to_index(offset, line_starts):
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return f"{lo + 1}.{offset - line_starts[lo]}"

    # ---------- Gutter (номера строк) ----------

    def _redraw_gutter(self):
        if self._updating_gutter:
            return
        self._updating_gutter = True
        g = self.gutter
        try:
            g.delete("all")
            if not self.winfo_ismapped() or self.winfo_height() < 5:
                return
            top_px = 1
            first_idx = self.index(f"@0,{top_px}")
            fv_line = int(first_idx.split(".")[0])
            height = self.winfo_height()
            total = self._line_no("end-1c")
            current = self._line_no()
            ln = fv_line
            while ln <= total:
                info = self.dlineinfo(ln)
                if not info:
                    break
                _, yy, _, hh, _ = info
                if yy > height:
                    break
                color = (self._colors["gutter_current_fg"] if ln == current
                         else self._colors["gutter_fg"])
                g.create_text(g.winfo_width() - 8, yy + hh // 2, anchor="e",
                              text=str(ln), fill=color, font=self._gutter_font)
                ln += 1
        except tk.TclError:
            pass
        finally:
            self._updating_gutter = False

    def destroy(self):
        try:
            self.completion_popup.hide()
        except Exception:
            pass
        try:
            self.gutter.destroy()
        except Exception:
            pass
        super().destroy()
