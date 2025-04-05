import tkinter as tk
from tkinter import ttk, filedialog
import time
from PIL import Image, ImageTk 

# Colors
BG_COLOR = "#BCDBDB"
ACCENT_COLOR = "#4A9590"
HIGHLIGHT_COLOR = "#BD6578"
TEXT_COLOR = "#B72B3D"
DARK_COLOR = "#4A0E1C"
CONTAINER_COLOR = "#D9D9D9"

class DiskberryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Diskberry Forensic Tool")
        self.geometry("800x600")
        self.configure(bg=BG_COLOR)
        self.frames = {}
        self.page_index = 0

        container = tk.Frame(self, bg=BG_COLOR)
        container.pack(fill="both", expand=True)

        for F in (SplashScreen, CaseManagementPage, DeviceSelectionPage, AcquisitionOptionsPage,
                  AcquisitionProgressPage, AcquisitionCompletePage):
            frame = F(container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame(SplashScreen)  # Start with SplashScreen

    def show_frame(self, cont):
        frame = self.frames[cont]
        frame.tkraise()
        self.update_idletasks()  # Force a refresh
        print(f"Raised frame: {cont.__name__}")  # Debugging output
        print(f"Frame visibility: {frame.winfo_ismapped()}")  # Check if the frame is visible

class BasePage(tk.Frame):
    def __init__(self, parent, controller, title):
        super().__init__(parent, bg=BG_COLOR)
        container = tk.Frame(self, bg=CONTAINER_COLOR, bd=2, relief="ridge")
        container.pack(fill="both", expand=True)  # Use pack instead of place

        self.container = container
        tk.Label(container, text=title, font=("Arial", 24), fg=TEXT_COLOR, bg=CONTAINER_COLOR).pack(pady=10)

class SplashScreen(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Diskberry Tool")
        print("Initializing SplashScreen...")  # Debugging output
        try:
            image_path = "C:/Users/talaa/OneDrive/Desktop/berry/splash2.png"  # Check this path exists!
            print(f"Loading image from: {image_path}")  # Debugging output
            img = Image.open(image_path)
            img = img.resize((300, 300))
            photo = ImageTk.PhotoImage(img)
            tk.Label(self.container, image=photo, bg=CONTAINER_COLOR).pack(pady=20)
            print("Image widget packed.")  # Debugging output
            self.image = photo  # Keep reference
            print("Image loaded successfully.")  # Debugging output
        except Exception as e:
            print(f"Image load error: {e}")  # Debugging output
            tk.Label(self.container, text="(Image failed to load)", fg=TEXT_COLOR, bg=CONTAINER_COLOR).pack(pady=20)

        tk.Button(self.container, text="Start", bg=ACCENT_COLOR,
                  command=lambda: controller.show_frame(CaseManagementPage)).pack(pady=10)
        print("Button widget packed.")  # Debugging output

class CaseManagementPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Management")
        fields = ["Case ID", "Investigator Name", "Notes"]
        self.entries = {}
        for idx, label in enumerate(fields):
            frame = tk.Frame(self.container, bg=CONTAINER_COLOR)
            frame.pack(pady=5)
            tk.Label(frame, text=label + ":", fg=TEXT_COLOR, bg=CONTAINER_COLOR, width=20, anchor="w").pack(side="left")
            entry = tk.Entry(frame, width=40)
            entry.pack(side="left")
            self.entries[label] = entry
        tk.Button(self.container, text="Next", bg=ACCENT_COLOR,
                  command=lambda: controller.show_frame(DeviceSelectionPage)).pack(pady=10)
        print(f"CaseManagementPage widgets: {[child.winfo_class() for child in self.container.winfo_children()]}")

class DeviceSelectionPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Device Selection")
        frame = tk.Frame(self.container, bg=CONTAINER_COLOR)
        frame.pack(pady=10)
        self.device_list = tk.Listbox(frame, width=50, height=6)
        self.device_list.pack(side="left", padx=10)
        tk.Button(frame, text="Refresh", bg=ACCENT_COLOR, command=self.refresh_devices).pack(side="left")
        tk.Button(self.container, text="Next", bg=ACCENT_COLOR,
                  command=lambda: controller.show_frame(AcquisitionOptionsPage)).pack(pady=10)

    def refresh_devices(self):
        self.device_list.delete(0, tk.END)
        self.device_list.insert(tk.END, "/dev/sda", "/dev/sdb")

class AcquisitionOptionsPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Acquisition Options")

        options = [
            ("Imaging Method", ["dd", "dcfldd"]),
            ("Output Format", ["Raw", "EWF", "AFF"]),
            ("Hashing Algorithm", ["SHA-256", "MD5"]),
        ]
        self.option_vars = {}

        for label, choices in options:
            frame = tk.Frame(self.container, bg=CONTAINER_COLOR)
            frame.pack(pady=5)
            tk.Label(frame, text=label + ":", fg=TEXT_COLOR, bg=CONTAINER_COLOR, width=20, anchor="w").pack(side="left")
            var = tk.StringVar()
            var.set(choices[0])
            tk.OptionMenu(frame, var, *choices).pack(side="left")
            self.option_vars[label] = var

        path_frame = tk.Frame(self.container, bg=CONTAINER_COLOR)
        path_frame.pack(pady=5)
        tk.Label(path_frame, text="Save Path:", fg=TEXT_COLOR, bg=CONTAINER_COLOR, width=20, anchor="w").pack(side="left")
        self.path_entry = tk.Entry(path_frame, width=30)
        self.path_entry.pack(side="left")
        tk.Button(path_frame, text="Browse", command=self.browse_path).pack(side="left")

        self.threading_var = tk.IntVar()
        self.bad_sectors_var = tk.IntVar()
        tk.Checkbutton(self.container, text="Threading", variable=self.threading_var, bg=CONTAINER_COLOR, fg=TEXT_COLOR).pack()
        tk.Checkbutton(self.container, text="Handle Bad Sectors", variable=self.bad_sectors_var, bg=CONTAINER_COLOR, fg=TEXT_COLOR).pack()

        tk.Button(self.container, text="Next", bg=ACCENT_COLOR,
                  command=lambda: controller.show_frame(AcquisitionProgressPage)).pack(pady=10)

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

class AcquisitionProgressPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Acquisition In Progress")
        self.progress = ttk.Progressbar(self.container, length=400, mode='determinate')
        self.progress.pack(pady=10)
        self.elapsed_label = tk.Label(self.container, text="Elapsed Time: 0s", bg=CONTAINER_COLOR, fg=TEXT_COLOR)
        self.elapsed_label.pack(pady=5)
        self.hash_field = tk.Entry(self.container, width=60)
        self.hash_field.pack(pady=5)
        self.hash_label = tk.Label(self.container, text="Hash Value:", bg=CONTAINER_COLOR, fg=TEXT_COLOR)
        self.hash_label.pack()
        tk.Button(self.container, text="Next", bg=ACCENT_COLOR,
                  command=lambda: controller.show_frame(AcquisitionCompletePage)).pack(pady=10)

class AcquisitionCompletePage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Acquisition Complete")
        tk.Label(self.container, text="An image has been acquired and the report has been successfully generated in a JSON format.",
                 wraplength=600, justify="center", bg=CONTAINER_COLOR, fg=TEXT_COLOR).pack(pady=20)
        tk.Button(self.container, text="Return to Main Menu", bg=ACCENT_COLOR,
                command=lambda: controller.show_frame(SplashScreen)).pack(pady=10)
        tk.Button(self.container, text="Close", bg=HIGHLIGHT_COLOR, command=self.quit).pack(pady=5)

if __name__ == "__main__":
    app = DiskberryApp()
    app.mainloop()
