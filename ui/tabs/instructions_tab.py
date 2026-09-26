import customtkinter as ctk

class InstructionsTabCTk(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.textbox = ctk.CTkTextbox(self, wrap="word", state="disabled")
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)

        plain_text = """Инструкция по использованию макроса
1. Редактор кода: слева пишется код, справа консоль вывода.
2. Выполнение: кнопка "Запустить" или хоткей. "Выключить" или тот же хоткей для остановки.
3. Хоткеи: выбираются в комбобоксе. Не конфликтуют с автокликером.
4. Доступные функции: wait(s), should_stop(), print(), keyboard, mouse, key_press, key_release, write, send, set_key, press_mouse, release_mouse, mouse_move, mouse_drag, mouse_position, mouse_is_pressed.
5. Пример:
print('Старт')
while not should_stop():
    key_press('A')
    click()
    wait(0.5)
print('Завершено')"""
        self.textbox.configure(state="normal")
        self.textbox.insert("1.0", plain_text)
        self.textbox.configure(state="disabled")