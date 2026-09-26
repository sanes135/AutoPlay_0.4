from ui.clicker_window import AutoClickerWindow
from config.settings import add_default_settings
from utils.helpers import resource_path

if __name__ == "__main__":
    add_default_settings()
    app = AutoClickerWindow()
    app.wm_attributes("-topmost", True)
    app.mainloop()