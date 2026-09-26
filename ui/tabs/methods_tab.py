import customtkinter as ctk

class MethodsTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.textbox = ctk.CTkTextbox(self, wrap="word", state="disabled")
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)

        plain_text = """key_press("клавиша") - зажимает конкретную клавишу
key_release("клавиша") - отпускает ранее зажатую клавишу.
key_tap("клавиша", delay=0.0) - обычное нажатие
write("текст", interval=0.0) - печатает переданный текст посимвольно.

mouse_click("кнопка") - делает однократный клик.
mouse_press("кнопка") - зажимает кнопку мыши и удерживает её.
mouse_release("кнопка") - отпускает ранее зажатую кнопку мыши.
mouse_move(x, y, absolute=False) - перемещает курсор.
mouse_drag(start_x, start_y, end_x, end_y, duration=0.0) - перетаскивает объект
mouse_position() - возвращает текущие координаты курсора в виде кортежа (x, y).
mouse_scroll(dx, dy) - прокручивает колесо мыши.

release_all() - экстренно отпускает все зажатые клавиши на клавиатуре и кнопки мыши.

Клавиши: space, enter, tab, backspace, delete, esc, shift, ctrl, alt, win (или cmd), caps_lock.
Стрелки: up, down, left, right.
Функциональные: f1, f2 и так далее до f12.
"""
        self.textbox.configure(state="normal")
        self.textbox.insert("1.0", plain_text)
        self.textbox.configure(state="disabled")