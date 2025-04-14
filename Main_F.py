#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import json
import os
import subprocess
from datetime import datetime
import hashlib
import re

####################################
# Helper Functions
####################################

def detect_devices():
    """
    Detect block devices (USB/disk drives) using lsblk.
    Returns a list of devices such as ['/dev/sda', '/dev/mmcblk0'].
    Skips non-disk (like loop) devices.
    """
    devices = []
    try:
        cmd = ["lsblk", "-o", "NAME,TYPE", "-P"]
        output = subprocess.check_output(cmd).decode("utf-8")
        for line in output.splitlines():
            parts = line.strip().split()
            name = ""
            dev_type = ""
            for part in parts:
                if part.startswith('NAME='):
                    name = part.split('=')[1].strip('"')
                elif part.startswith('TYPE='):
                    dev_type = part.split('=')[1].strip('"')
            if dev_type == "disk":
                devices.append(f"/dev/{name}")
    except Exception as e:
        print(f"Error detecting devices: {e}")
    return devices

def compute_hash(filepath, hash_algo):
    """
    Compute the hash of file at `filepath` using hashlib.
    Returns the digest as a hex string.
    """
    BLOCKSIZE = 65536
    if hash_algo.lower() == "md5":
        hasher = hashlib.md5()
    else:
        hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            buf = f.read(BLOCKSIZE)
            while buf:
                hasher.update(buf)
                buf = f.read(BLOCKSIZE)
        return hasher.hexdigest()
    except Exception as e:
        return f"Error computing hash: {e}"

def get_device_info(device):
    """
    Extract detailed information about the device using smartctl.
    Returns a dictionary with device details.
    """
    device_info = {}
    try:
        # Check if smartctl is installed
        subprocess.check_output(["which", "smartctl"], text=True)
        output = subprocess.check_output(["sudo", "smartctl", "-i", device], text=True)
        for line in output.splitlines():
            if ":" in line:
                key, value = map(str.strip, line.split(":", 1))
                device_info[key] = value
    except subprocess.CalledProcessError:
        device_info["Error"] = "smartctl not found or failed to execute. Please install smartmontools."
    except Exception as e:
        print(f"Error getting device info: {e}")
        device_info["Error"] = str(e)
    return device_info

def count_deleted_files(device, filesystem_type=None):
    """
    Count the number of deleted files on the device or raw image using fls.
    If the file system type is known, it can be specified with the `filesystem_type` parameter.
    Returns the count of deleted files.
    """
    deleted_count = 0
    try:
        # Build the fls command
        cmd = ["sudo", "fls", "-r"]
        if filesystem_type:
            cmd.extend(["-f", filesystem_type])
        cmd.append(device)

        # Run the fls command
        output = subprocess.check_output(cmd, text=True)
        for line in output.splitlines():
            if " (deleted)" in line:
                deleted_count += 1
    except subprocess.CalledProcessError as e:
        print(f"fls failed: {e}")
        deleted_count = -1  # Indicate an error
    except Exception as e:
        print(f"Error counting deleted files: {e}")
        deleted_count = -1  # Indicate an error
    return deleted_count

def detect_filesystem_type(image_path):
    """
    Detect the file system type of a raw image using the `file` command.
    Returns the file system type as a string, or None if it cannot be determined.
    """
    try:
        output = subprocess.check_output(["file", image_path], text=True)
        if "NTFS" in output:
            return "ntfs"
        elif "FAT" in output:
            return "fat"
        elif "ext4" in output:
            return "ext4"
        elif "ext3" in output:
            return "ext3"
        elif "ext2" in output:
            return "ext2"
        else:
            print(f"Unknown file system type: {output}")
            return None
    except Exception as e:
        print(f"Error detecting file system type: {e}")
        return None

def check_dependencies():
    """
    Check if required tools (smartctl, fls) are installed.
    """
    missing_tools = []
    try:
        subprocess.check_output(["which", "smartctl"], text=True)
    except subprocess.CalledProcessError:
        missing_tools.append("smartctl (smartmontools)")

    try:
        subprocess.check_output(["which", "fls"], text=True)
    except subprocess.CalledProcessError:
        missing_tools.append("fls (sleuthkit)")

    if missing_tools:
        messagebox.showerror(
            "Missing Dependencies",
            f"The following tools are required but not installed:\n- " + "\n- ".join(missing_tools) +
            "\n\nPlease install them and try again."
        )
        return False
    return True

####################################
# Main Application and GUI Pages
####################################
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        if not check_dependencies():
            self.destroy()
            return
        self.title("Disk Acquisition Tool")
        self.geometry("700x550")
        self.shared_data = {
            "case_id": "",
            "investigator": "",
            "notes": "",
            "device": "",
            "imaging_method": "",   # "dd" or "dcfldd"
            "output_format": "",    # "raw" or "ewf"
            "hash_algorithm": "",   # "SHA-256" or "MD5"
            "save_path": "",
            "threading_option": False,
            "bad_sectors_option": False,
            "block_size": "4M",     # New: Block size selected by the user.
            "hash_value": "",
            "status": "",
            "image_file": ""
        }
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        self.frames = {}
        for F in (CaseInfoPage, DeviceSelectionPage, AcquisitionOptionsPage,
                  AcquisitionProgressPage, CompletionPage):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")
        self.show_frame("CaseInfoPage")

    def show_frame(self, page_name):
        frame = self.frames[page_name]
        frame.tkraise()


####################################
# Page 1: Case Information Page
####################################
class CaseInfoPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        tk.Label(self, text="Enter Case Information", font=("Helvetica", 16)).pack(pady=10)

        tk.Label(self, text="Case ID:").pack()
        self.case_id_entry = tk.Entry(self, width=50)
        self.case_id_entry.pack(pady=5)

        tk.Label(self, text="Investigator Name:").pack()
        self.investigator_entry = tk.Entry(self, width=50)
        self.investigator_entry.pack(pady=5)

        tk.Label(self, text="Notes:").pack()
        self.notes_text = tk.Text(self, height=4, width=50)
        self.notes_text.pack(pady=5)

        tk.Button(self, text="Next", command=self.save_and_next).pack(pady=20)

    def save_and_next(self):
        self.controller.shared_data["case_id"] = self.case_id_entry.get().strip()
        self.controller.shared_data["investigator"] = self.investigator_entry.get().strip()
        self.controller.shared_data["notes"] = self.notes_text.get("1.0", tk.END).strip()

        if not self.controller.shared_data["case_id"] or not self.controller.shared_data["investigator"]:
            messagebox.showerror("Error", "Please enter both Case ID and Investigator Name.")
            return
        self.controller.show_frame("DeviceSelectionPage")


####################################
# Page 2: Device Selection Page
####################################
class DeviceSelectionPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        tk.Label(self, text="Select Device for Acquisition", font=("Helvetica", 16)).pack(pady=10)

        self.devices = detect_devices()
        if not self.devices:
            self.devices = ["No devices found"]
        self.selected_device = tk.StringVar(value=self.devices[0])

        tk.Label(self, text="Available Devices:").pack(pady=5)
        self.device_menu = ttk.Combobox(self, textvariable=self.selected_device,
                                        values=self.devices, state="readonly", width=30)
        self.device_menu.pack(pady=5)

        tk.Button(self, text="Next", command=self.save_and_next).pack(pady=20)

    def save_and_next(self):
        device = self.selected_device.get()
        if device == "No devices found":
            messagebox.showerror("Error", "No USB or disk devices detected.")
            return
        self.controller.shared_data["device"] = device
        self.controller.show_frame("AcquisitionOptionsPage")


####################################
# Page 3: Acquisition Options Page
####################################
class AcquisitionOptionsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        tk.Label(self, text="Acquisition Options", font=("Helvetica", 16)).pack(pady=10)

        # Imaging Method: dd or dcfldd
        tk.Label(self, text="Image Method:").pack(pady=2)
        self.imaging_method = tk.StringVar(value="dd")
        tk.Radiobutton(self, text="dd", variable=self.imaging_method, value="dd").pack()
        tk.Radiobutton(self, text="dcfldd", variable=self.imaging_method, value="dcfldd").pack()

        # Output Format: raw or ewf
        tk.Label(self, text="Output Format:").pack(pady=2)
        self.output_format = tk.StringVar(value="raw")
        tk.Radiobutton(self, text="Raw", variable=self.output_format, value="raw").pack()
        tk.Radiobutton(self, text="EWF", variable=self.output_format, value="ewf").pack()

        # Hash Algorithm: SHA-256 or MD5
        tk.Label(self, text="Hash Algorithm:").pack(pady=2)
        self.hash_algorithm = tk.StringVar(value="SHA-256")
        tk.Radiobutton(self, text="SHA-256", variable=self.hash_algorithm, value="SHA-256").pack()
        tk.Radiobutton(self, text="MD5", variable=self.hash_algorithm, value="MD5").pack()

        # Save Path Selection
        tk.Label(self, text="Save Path:").pack(pady=2)
        path_frame = tk.Frame(self)
        path_frame.pack(pady=5)
        self.save_path_entry = tk.Entry(path_frame, width=40)
        self.save_path_entry.pack(side="left")
        tk.Button(path_frame, text="Browse", command=self.browse_path).pack(side="left", padx=5)

        # Block Size Selection (New)
        tk.Label(self, text="Block Size (e.g., 1M, 2M, 4M, 8M, 16M):").pack(pady=2)
        self.block_size = tk.StringVar(value="4M")
        block_options = ["1M", "2M", "4M", "8M", "16M"]
        self.block_size_menu = ttk.Combobox(self, textvariable=self.block_size,
                                            values=block_options, state="readonly", width=10)
        self.block_size_menu.pack(pady=5)

        # Options for Threading and Bad Sectors
        self.threading_option = tk.IntVar(value=1)
        self.bad_sectors_option = tk.IntVar(value=1)
        tk.Checkbutton(self, text="Use Threading", variable=self.threading_option).pack(pady=2)
        tk.Checkbutton(self, text="Scan for Bad Sectors", variable=self.bad_sectors_option).pack(pady=2)

        tk.Button(self, text="Start Acquisition", command=self.save_and_start).pack(pady=20)

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.save_path_entry.delete(0, tk.END)
            self.save_path_entry.insert(0, path)

    def save_and_start(self):
        sd = self.controller.shared_data
        sd["imaging_method"] = self.imaging_method.get()
        sd["output_format"] = self.output_format.get()
        sd["hash_algorithm"] = self.hash_algorithm.get()
        sd["save_path"] = self.save_path_entry.get().strip()
        sd["threading_option"] = bool(self.threading_option.get())
        sd["bad_sectors_option"] = bool(self.bad_sectors_option.get())
        sd["block_size"] = self.block_size.get()

        if not sd["save_path"] or not os.path.isdir(sd["save_path"]):
            messagebox.showerror("Error", "Please select a valid save path.")
            return

        self.controller.show_frame("AcquisitionProgressPage")
        progress_page = self.controller.frames["AcquisitionProgressPage"]
        progress_page.start_acquisition()


####################################
# Page 4: Acquisition Progress Page
####################################
class AcquisitionProgressPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.acquisition_thread = None

        tk.Label(self, text="Acquisition in Progress", font=("Helvetica", 16)).pack(pady=10)

        # Progress bar that will be updated in real time
        self.progress = ttk.Progressbar(self, orient="horizontal", length=500,
                                        mode="determinate", maximum=100)
        self.progress.pack(pady=10)

        # Status label for progress text
        self.status_label = tk.Label(self, text="Starting acquisition...")
        self.status_label.pack(pady=5)

        # Next button (disabled until process completes)
        self.next_btn = tk.Button(self, text="Next", state="disabled", command=self.finish)
        self.next_btn.pack(pady=20)

    def start_acquisition(self):
        # Start in a separate thread so GUI stays responsive
        self.acquisition_thread = threading.Thread(target=self.run_acquisition)
        self.acquisition_thread.start()

    def run_acquisition(self):
        data = self.controller.shared_data
        device = data["device"]
        method = data["imaging_method"]
        hash_algo = data["hash_algorithm"]
        save_path = data["save_path"]
        output_format = data["output_format"]
        block_size = data.get("block_size", "4M")
        print(f"[DEBUG] Using block size: {block_size}")

        # Determine total size using blockdev
        try:
            output = subprocess.check_output(["sudo", "blockdev", "--getsize64", device])
            total_size = int(output.strip())
        except Exception as e:
            total_size = None
            print(f"Error getting total size: {e}")

        extension = "img" if output_format.lower() == "raw" else output_format.lower()
        image_file = os.path.join(save_path, f"disk_image.{extension}")

        if method == "dd":
            # Build the dd command with chosen block size and status=progress to get real-time updates
            dd_cmd = [
                "sudo", "dd",
                f"if={device}",
                f"of={image_file}",
                f"bs={block_size}",
                "conv=noerror,sync",
                "status=progress"
            ]
            print(f"[DEBUG] dd command: {' '.join(dd_cmd)}")  # Debugging statement
            try:
                process = subprocess.Popen(dd_cmd, stderr=subprocess.PIPE, text=True)
            except Exception as e:
                self.progress.after(0, self.on_acquisition_error, str(e))
                return

            # Use regex to extract bytes copied from each line of stderr
            pattern = re.compile(r"(\d+)\s+bytes")
            copied_bytes = 0

            # Read dd progress output line by line
            for line in iter(process.stderr.readline, ""):
                match = pattern.search(line)
                if match:
                    try:
                        copied_bytes = int(match.group(1))
                        if total_size:
                            progress_pct = (copied_bytes / total_size) * 100
                            # Update progress bar and status label (using after() to run in main thread)
                            self.progress.after(0, lambda pct=progress_pct: self.progress.config(value=pct))
                            self.status_label.after(0, lambda: self.status_label.config(
                                text=f"{copied_bytes} bytes copied ({progress_pct:.1f}%)"
                            ))
                    except Exception as e:
                        print(f"Error parsing progress: {e}")
            process.wait()
            if process.returncode != 0:
                error_text = f"dd error: code {process.returncode}"
                self.progress.after(0, self.on_acquisition_error, error_text)
                return

            # After dd completes, compute hash
            computed_hash = compute_hash(image_file, hash_algo)
            data["hash_value"] = computed_hash
            data["image_file"] = image_file

        elif method == "dcfldd":
            # For this example, we focus on dd.
            # Implement dcfldd acquisition similarly if needed.
            self.progress.after(0, self.on_acquisition_error, "dcfldd method not implemented")
            return

        data["status"] = "Complete"
        self.progress.after(0, self.on_acquisition_complete)

    def on_acquisition_error(self, error_msg):
        print(f"[DEBUG] Acquisition error: {error_msg}")
        self.status_label.config(text=f"Acquisition Error: {error_msg}")
        self.next_btn.config(state="normal")

    def on_acquisition_complete(self):
        print("[DEBUG] Acquisition complete. Updating GUI.")  # Debugging statement
        self.status_label.config(text=f"Acquisition Complete. Hash: {self.controller.shared_data['hash_value']}")
        self.next_btn.config(state="normal")  # Enable the "Next" button
        print(f"[DEBUG] Next button state: {self.next_btn['state']}")  # Debugging statement

    def finish(self):
        self.controller.show_frame("CompletionPage")


####################################
# Page 5: Completion / Report Page
####################################
class CompletionPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.status_message = tk.Label(self, text="", font=("Helvetica", 16))
        self.status_message.pack(pady=10)

        self.report_text = tk.Text(self, height=12, width=70)
        self.report_text.pack(pady=10)

        tk.Button(self, text="Generate Report and Save", command=self.generate_report).pack(pady=10)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        status = self.controller.shared_data.get("status", "Unknown")
        if status == "Complete":
            self.status_message.config(text="Acquisition Complete!")
        else:
            self.status_message.config(text=status)
        self.report_text.delete("1.0", tk.END)

    def generate_report(self):
        data = self.controller.shared_data

        # Get detailed device information
        device_info = get_device_info(data["device"])

        # Detect file system type for raw images
        filesystem_type = detect_filesystem_type(data["device"])
        if not filesystem_type:
            self.report_text.insert(tk.END, "Error: Could not determine file system type.\n")
            return

        # Count deleted files
        deleted_files_count = count_deleted_files(data["device"], filesystem_type)

        # Prepare the report data
        report = {
            "case_id": data["case_id"],
            "investigator": data["investigator"],
            "notes": data["notes"],
            "device": data["device"],
            "device_info": device_info,
            "deleted_files_count": deleted_files_count,
            "acquisition_options": {
                "imaging_method": data["imaging_method"],
                "output_format": data["output_format"],
                "hash_algorithm": data["hash_algorithm"],
                "threading": data["threading_option"],
                "bad_sectors": data["bad_sectors_option"],
                "block_size": data["block_size"]
            },
            "save_path": data["save_path"],
            "image_file": data.get("image_file", ""),
            "hash_value": data["hash_value"],
            "status": data["status"],
            "timestamp": datetime.now().isoformat()
        }

        # Generate JSON and HTML reports (as before)
        # Generate JSON report
        json_filename = f"case_{data['case_id']}_{int(time.time())}.json"
        json_full_path = os.path.join(data["save_path"], json_filename)

        try:
            with open(json_full_path, "w") as f:
                json.dump(report, f, indent=4)
            self.report_text.insert(tk.END, f"JSON Report generated and saved to:\n{json_full_path}\n")
        except Exception as e:
            self.report_text.insert(tk.END, f"Error generating JSON report: {e}\n")

        # Generate HTML report
        html_filename = f"case_{data['case_id']}_{int(time.time())}.html"
        html_full_path = os.path.join(data["save_path"], html_filename)

        html_content = f"""
        <html>
        <head>
            <title>Acquisition Report - Case {data['case_id']}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>Acquisition Report</h1>
            <p><strong>Case ID:</strong> {data['case_id']}</p>
            <p><strong>Investigator:</strong> {data['investigator']}</p>
            <p><strong>Notes:</strong> {data['notes']}</p>
            <p><strong>Device:</strong> {data['device']}</p>
            <h2>Device Information</h2>
            <table>
                <tr><th>Attribute</th><th>Value</th></tr>
                {''.join(f"<tr><td>{key}</td><td>{value}</td></tr>" for key, value in device_info.items())}
            </table>
            <h2>Acquisition Options</h2>
            <table>
                <tr><th>Option</th><th>Value</th></tr>
                <tr><td>Imaging Method</td><td>{data['imaging_method']}</td></tr>
                <tr><td>Output Format</td><td>{data['output_format']}</td></tr>
                <tr><td>Hash Algorithm</td><td>{data['hash_algorithm']}</td></tr>
                <tr><td>Threading</td><td>{data['threading_option']}</td></tr>
                <tr><td>Bad Sectors</td><td>{data['bad_sectors_option']}</td></tr>
                <tr><td>Block Size</td><td>{data['block_size']}</td></tr>
            </table>
            <h2>Results</h2>
            <p><strong>Save Path:</strong> {data['save_path']}</p>
            <p><strong>Image File:</strong> {data.get('image_file', '')}</p>
            <p><strong>Hash Value:</strong> {data['hash_value']}</p>
            <p><strong>Deleted Files Count:</strong> {deleted_files_count}</p>
            <p><strong>Status:</strong> {data['status']}</p>
            <p><strong>Timestamp:</strong> {datetime.now().isoformat()}</p>
        </body>
        </html>
        """

        try:
            with open(html_full_path, "w") as f:
                f.write(html_content)
            self.report_text.insert(tk.END, f"HTML Report generated and saved to:\n{html_full_path}\n")
        except Exception as e:
            self.report_text.insert(tk.END, f"Error generating HTML report: {e}\n")


####################################
# Main Execution
####################################
if __name__ == "__main__":
    app = App()
    app.mainloop()