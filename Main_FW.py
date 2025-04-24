#!/usr/bin/env python3
import os
import re
import json
import time
import platform
import logging
import subprocess
import threading
import hashlib
import sys

from datetime import datetime
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from pathlib import Path

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox

if platform.system() == "Windows":
    import win32com.client
    import winreg

# ----------------------
# Constants & Configuration
# ----------------------
LOG_FILE = f"disk_tool_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
MAX_LOG_SIZE = 2_000_000  # 2MB
LOG_BACKUP_COUNT = 3
DEFAULT_BLOCK_SIZE = "4M"
HASH_BUFFER_SIZE = 4 * 1024 * 1024  # 4MB buffer for hashing
SUPPORTED_FILESYSTEMS = (
    "ntfs", "fat32", "exfat", "fat", 
    "ext4", "ext3", "ext2", "xfs", "btrfs"
)

# ----------------------
# Logging Configuration
# ----------------------
def setup_logging():
    """Configure logging with rotation and formatting."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_LOG_SIZE,
        backupCount=LOG_BACKUP_COUNT
    )
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "[%(levelname)s] %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

setup_logging()
logger = logging.getLogger(__name__)

# Executors for concurrency
IO_EXECUTOR = ThreadPoolExecutor(max_workers=4)
CPU_EXECUTOR = ProcessPoolExecutor(max_workers=os.cpu_count() or 4)

# ----------------------
# Helper Functions
# ----------------------

def run_command(cmd, check=True, **kwargs):
    """Run a system command with error handling."""
    try:
        return subprocess.run(
            cmd,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **kwargs
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(cmd)}")
        logger.error(f"Error: {e.stderr.strip()}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error running command: {' '.join(cmd)}")
        raise

def detect_devices():
    """Detect available storage devices."""
    try:
        if platform.system() == "Linux":
            result = run_command(["lsblk", "-o", "NAME,TYPE", "-P"])
            devices = []
            for line in result.stdout.splitlines():
                m = re.search(r'NAME="(?P<name>[^\"]+)"\s+TYPE="disk"', line)
                if m:
                    devices.append(f"/dev/{m.group('name')}")
            return devices
        elif platform.system() == "Windows":
            result = run_command(["wmic", "logicaldisk", "get", "name"])
            return [
                f"{line.strip()}\\"
                for line in result.stdout.splitlines() 
                if line.strip().endswith(":")
            ]
        else:
            logger.warning("Unsupported OS for device detection")
            return []
    except Exception:
        logger.exception("Failed to detect devices")
        return []

def compute_hash(filepath, algo="sha256"):
    """Compute hash of a file using specified algorithm."""
    hash_algo = {
        "md5": hashlib.md5,
        "sha256": hashlib.sha256
    }.get(algo.lower(), hashlib.sha256)
    
    h = hash_algo()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(HASH_BUFFER_SIZE), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        logger.exception(f"Hashing failed for {filepath}")
        return None

def count_deleted_files(image_path, fstype=None):
    """Count deleted files in a disk image using fls."""
    try:
        cmd = ["fls", "-r"]
        if fstype:
            cmd.extend(["-f", fstype])
        cmd.append(image_path)
        
        result = run_command(cmd, check=False)
        if result.returncode != 0:
            logger.warning(f"fls returned {result.returncode}: {result.stderr}")
            return 0
            
        return sum(1 for line in result.stdout.splitlines() if "(deleted)" in line)
    except Exception:
        logger.exception("Deleted-file counting failed")
        return 0

def detect_filesystem_type(path):
    """Detect filesystem type of a device or image."""
    try:
        if os.path.exists(path) and path.startswith("/dev/"):
            result = run_command(["lsblk", "-no", "FSTYPE", path])
            fs = result.stdout.strip()
            return fs.lower() if fs else None
        else:
            result = run_command(["file", "-s", path])
            for fs in SUPPORTED_FILESYSTEMS:
                if fs.upper() in result.stdout.upper():
                    return fs
            return None
    except Exception:
        logger.exception(f"Filesystem detection failed for {path}")
        return None

def get_device_info(device):
    """Get detailed information about a storage device."""
    info = {}
    try:
        result = run_command(
            ["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT", "-P", device]
        )
        for line in result.stdout.splitlines():
            for part in line.split():
                if "=" in part:
                    k, v = part.split("=", 1)
                    info[k] = v.strip('"')
    except Exception:
        logger.exception(f"Failed to get device info for {device}")
    return info

def get_usb_details():
    """Get USB device information."""
    if platform.system() == "Windows":
        return get_usb_details_windows()
    elif platform.system() == "Linux":
        return get_usb_details_linux()
    else:
        logger.warning("Unsupported OS for USB details extraction.")
        return []

def get_usb_details_windows():
    """Extract detailed USB information on Windows."""
    usb_details = []
    try:
        wmi = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        service = wmi.ConnectServer(".", "root\\cimv2")
        devices = service.ExecQuery("SELECT * FROM Win32_USBHub")

        for device in devices:
            details = {
                "Vendor": device.Manufacturer,
                "Product": device.Name,
                "Device GUID": device.DeviceID,
                "Serial Number": device.PNPDeviceID.split("\\")[-1]
            }

            try:
                reg_path = r"SYSTEM\\CurrentControlSet\\Enum\\" + device.PNPDeviceID.replace("\\", "\\\\")
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                    details["Vendor ID"] = winreg.QueryValueEx(key, "VendorID")[0]
                    details["Product ID"] = winreg.QueryValueEx(key, "ProductID")[0]
            except Exception as e:
                details["Registry Error"] = str(e)

            usb_details.append(details)
    except Exception as e:
        logger.exception(f"Failed to retrieve USB details: {e}")
    return usb_details

def get_usb_details_linux():
    """Extract detailed USB information on Linux."""
    usb_details = []
    try:
        lsusb = run_command(["lsusb"])
        for line in lsusb.stdout.splitlines():
            parts = line.split()
            if len(parts) < 6:
                continue
                
            bus = parts[1]
            dev = parts[3].strip(":")
            vid_pid = parts[5].split(":")

            udev = run_command(["udevadm", "info", f"/dev/bus/usb/{bus}/{dev}"])
            details = {
                "Bus": bus,
                "Device": dev,
                "VendorID": vid_pid[0],
                "ProductID": vid_pid[1]
            }

            for udev_line in udev.stdout.splitlines():
                if udev_line.startswith("E:"):
                    k, v = udev_line[2:].split("=", 1)
                    details[k] = v

            usb_details.append(details)
    except Exception:
        logger.exception("Failed to retrieve USB info")
    return usb_details

def generate_html_report(data, device_info, deleted_count, usb_info):
    """Generate an HTML report of the acquisition."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_file = os.path.join(
        data["save_path"], 
        f"report_{data['case_id']}_{int(time.time())}.html"
    )
    
    # Generate USB info HTML
    usb_html = ""
    for usb in usb_info:
        usb_html += '<div class="table-responsive"><table class="table table-bordered table-striped">'
        usb_html += '<thead><tr><th>Attribute</th><th>Value</th></tr></thead><tbody>'
        for k, v in usb.items():
            usb_html += f'<tr><td>{k}</td><td>{v}</td></tr>'
        usb_html += '</tbody></table></div>'
    
    # Generate device info HTML
    dev_html = '<div class="table-responsive"><table class="table table-bordered table-striped">'
    dev_html += '<thead><tr><th>Attribute</th><th>Value</th></tr></thead><tbody>'
    for k, v in device_info.items():
        dev_html += f'<tr><td>{k}</td><td>{v}</td></tr>'
    dev_html += '</tbody></table></div>'
    
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Acquisition Report</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
</head>
<body>
  <div class="container my-4">
    <h1 class="mb-4">Disk Acquisition Report</h1>
    
    <h3>Case Details</h3>
    <ul>
      <li><strong>Case ID:</strong> {data['case_id']}</li>
      <li><strong>Investigator:</strong> {data['investigator']}</li>
      <li><strong>Notes:</strong> {data['notes']}</li>
      <li><strong>Device:</strong> {data['device']}</li>
      <li><strong>Timestamp:</strong> {timestamp}</li>
    </ul>
    
    <h3 class="mt-4">Device Information</h3>
    {dev_html}
    
    <h3 class="mt-4">USB Information</h3>
    {usb_html}
    
    <h3 class="mt-4">Results</h3>
    <ul>
      <li><strong>Image File:</strong> {data['image_file']}</li>
      <li><strong>Hash Value:</strong> <code>{data['hash_value']}</code></li>
      <li><strong>Deleted Files:</strong> {deleted_count}</li>
    </ul>
  </div>
</body>
</html>"""
    
    try:
        with open(report_file, "w") as f:
            f.write(html_template)
        return report_file
    except Exception:
        logger.exception("Failed to write HTML report")
        return None

# ----------------------
# GUI Classes
# ----------------------
class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        if not self.check_deps():
            self.destroy()
            return

        self.title("Disk Acquisition Tool")
        self.geometry("800x600")

        self.shared = {
            "case_id": "", "investigator": "", "notes": "",
            "device": "", "imaging_method": "", "output_format": "",
            "hash_algorithm": "", "save_path": "", "block_size": "4M",
            "threading_option": True, "bad_sectors_option": True,
            "image_file": "", "hash_value": "", "status": ""
        }

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        self.frames = {}
        for F in (CaseInfoPage, DeviceSelectionPage, AcquisitionOptionsPage,
                  AcquisitionProgressPage, CompletionPage):
            page = F(container, self)
            self.frames[F.__name__] = page
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show_frame("CaseInfoPage")

    def show_frame(self, name):
        self.frames[name].tkraise()

    def check_deps(self):
        required = {
            "Linux": ["dd", "lsblk", "file", "fls", "udevadm", "lsusb"],
            "Windows": ["wmic"]
        }
        current_os = platform.system()
        missing = []
        
        for tool in required.get(current_os, []):
            try:
                run_command(["where" if current_os == "Windows" else "which", tool], check=True)
            except Exception:
                missing.append(tool)
                
        if missing:
            messagebox.showerror("Missing Dependencies", "Please install: " + ", ".join(missing))
            return False
        return True

class CaseInfoPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.ctrl = controller
        ttk.Label(self, text="Case Information", font=("Helvetica", 18)).pack(pady=20)
        form = ttk.Frame(self)
        form.pack(pady=10)
        ttk.Label(form, text="Case ID:").grid(row=0, column=0, sticky=W, pady=5)
        self.case_id = ttk.Entry(form, width=40)
        self.case_id.grid(row=0, column=1, pady=5)
        ttk.Label(form, text="Investigator:").grid(row=1, column=0, sticky=W, pady=5)
        self.inv = ttk.Entry(form, width=40)
        self.inv.grid(row=1, column=1, pady=5)
        ttk.Label(form, text="Notes:").grid(row=2, column=0, sticky=NW, pady=5)
        self.notes = ttk.Text(form, width=40, height=4)
        self.notes.grid(row=2, column=1, pady=5)
        ttk.Button(self, text="Next", bootstyle="primary",
                   command=self.next).pack(pady=20)

    def next(self):
        cid = self.case_id.get().strip()
        inv = self.inv.get().strip()
        if not cid or not inv:
            messagebox.showwarning("Input Error", "Case ID and Investigator are required.")
            return
        self.ctrl.shared["case_id"] = cid
        self.ctrl.shared["investigator"] = inv
        self.ctrl.shared["notes"] = self.notes.get("1.0", "end").strip()
        self.ctrl.show_frame("DeviceSelectionPage")

class DeviceSelectionPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.ctrl = controller
        ttk.Label(self, text="Select Device", font=("Helvetica", 18)).pack(pady=20)
        self.device_var = ttk.StringVar()
        self.combo = ttk.Combobox(self, textvariable=self.device_var, state="readonly", width=50)
        self.combo.pack(pady=10)
        ttk.Button(self, text="Rescan", bootstyle="secondary",
                   command=self.scan).pack(pady=5)
        ttk.Button(self, text="Next", bootstyle="primary",
                   command=self.next).pack(pady=20)
        self.scan()

    def scan(self):
        self.combo["values"] = ["Scanning..."]
        self.device_var.set("Scanning...")
        def task():
            devs = detect_devices() or ["No devices found"]
            self.after(0, lambda: self.combo.configure(values=devs))
            self.after(0, lambda: self.device_var.set(devs[0]))
        IO_EXECUTOR.submit(task)

    def next(self):
        dev = self.device_var.get()
        if not dev or dev == "No devices found":
            messagebox.showerror("Error", "No device selected.")
            return
        self.ctrl.shared["device"] = dev
        self.ctrl.show_frame("AcquisitionOptionsPage")

class AcquisitionOptionsPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.ctrl = controller
        ttk.Label(self, text="Acquisition Options", font=("Helvetica", 18)).pack(pady=20)
        form = ttk.Frame(self)
        form.pack(pady=10)

        # Imaging Method
        ttk.Label(form, text="Method:").grid(row=0, column=0, sticky=W, pady=
            5)
                # Imaging Method (continued)
        self.method = ttk.StringVar(value="dd")
        ttk.Radiobutton(form, text="dd", variable=self.method, value="dd").grid(row=0, column=1)
        ttk.Radiobutton(form, text="dcfldd", variable=self.method, value="dcfldd").grid(row=0, column=2)

        # Output Format
        ttk.Label(form, text="Format:").grid(row=1, column=0, sticky=W, pady=5)
        self.fmt = ttk.StringVar(value="raw")
        ttk.Radiobutton(form, text="Raw", variable=self.fmt, value="raw").grid(row=1, column=1)
        ttk.Radiobutton(form, text="EWF", variable=self.fmt, value="ewf").grid(row=1, column=2)

        # Hash Algorithm
        ttk.Label(form, text="Hash:").grid(row=2, column=0, sticky=W, pady=5)
        self.hashalg = ttk.StringVar(value="sha256")
        ttk.Radiobutton(form, text="SHA-256", variable=self.hashalg, value="sha256").grid(row=2, column=1)
        ttk.Radiobutton(form, text="MD5", variable=self.hashalg, value="md5").grid(row=2, column=2)

        # Save Path
        ttk.Label(form, text="Save Path:").grid(row=3, column=0, sticky=W, pady=5)
        self.savepath = ttk.Entry(form, width=40)
        self.savepath.grid(row=3, column=1)
        ttk.Button(form, text="Browse", bootstyle="secondary",
                 command=self.browse).grid(row=3, column=2, padx=5)

        # Block Size
        ttk.Label(form, text="Block Size:").grid(row=4, column=0, sticky=W, pady=5)
        self.block = ttk.Combobox(form, values=["1M","4M","8M","16M"],
                                state="readonly", width=8)
        self.block.set("4M")
        self.block.grid(row=4, column=1, pady=5)

        ttk.Button(self, text="Start Acquisition", bootstyle="primary",
                 command=self.start).pack(pady=20)

    def browse(self):
        path = filedialog.askdirectory()
        if path:
            self.savepath.delete(0, "end")
            self.savepath.insert(0, path)

    def start(self):
        sd = self.ctrl.shared
        sd.update({
            "imaging_method": self.method.get(),
            "output_format": self.fmt.get(),
            "hash_algorithm": self.hashalg.get(),
            "save_path": self.savepath.get().strip(),
            "block_size": self.block.get()
        })
        
        if not sd["save_path"] or not os.path.isdir(sd["save_path"]):
            messagebox.showerror("Error", "Please select a valid directory.")
            return
            
        self.ctrl.show_frame("AcquisitionProgressPage")
        self.ctrl.frames["AcquisitionProgressPage"].begin()

class AcquisitionProgressPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.ctrl = controller
        ttk.Label(self, text="Acquisition Progress", font=("Helvetica", 18)).pack(pady=20)
        
        self.progress = ttk.Progressbar(self, orient="horizontal", 
                                      mode="determinate", length=400)
        self.progress.pack(pady=10)
        
        self.status_label = ttk.Label(self, text="Preparing acquisition...")
        self.status_label.pack(pady=5)
        
        self.log_text = ttk.Text(self, height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=20, pady=10)
        
        nav_frame = ttk.Frame(self)
        nav_frame.pack(pady=10)
        
        ttk.Button(nav_frame, text="Cancel", bootstyle="danger",
                 command=self.cancel).pack(side="left", padx=5)
        
        self.next_btn = ttk.Button(nav_frame, text="Next", bootstyle="success",
                                 state="disabled", command=self.next_step)
        self.next_btn.pack(side="right", padx=5)

    def begin(self):
        self.thread = threading.Thread(target=self.run_acquisition, daemon=True)
        self.thread.start()

    def run_acquisition(self):
        sd = self.ctrl.shared
        device = sd["device"]
        ext = "img" if sd["output_format"] == "raw" else "ewf"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(sd["save_path"], f"{sd['case_id']}_{timestamp}.{ext}")
        sd["image_file"] = output_file

        # Get device size for progress calculation
        try:
            size_cmd = ["blockdev", "--getsize64", device]
            size_result = subprocess.run(size_cmd, capture_output=True, text=True, check=True)
            size_output = size_result.stdout.strip()

            if not size_output.isdigit():
                raise ValueError(f"Invalid device size output: {size_output}")

            total_size = int(size_output)
            self.progress["maximum"] = total_size
        except subprocess.CalledProcessError as e:
            logger.error(f"blockdev command failed: {e.stderr.strip()}")
            messagebox.showerror("Error", f"Failed to get device size: {e.stderr.strip()}")
            return
        except ValueError as e:
            logger.error(str(e))
            messagebox.showerror("Error", str(e))
            return
        except Exception as e:
            logger.exception("Unexpected error while getting device size")
            messagebox.showerror("Error", "Unexpected error occurred while getting device size.")
            return

        # Build acquisition command
        cmd = [
            "sudo", sd["imaging_method"],
            f"if={device}",
            f"of={output_file}",
            f"bs={sd['block_size']}",
            "status=progress"
        ]
        
        if sd["bad_sectors_option"]:
            cmd.append("conv=noerror,sync")

        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            # Regex to parse progress
            progress_re = re.compile(r"(\d+) bytes.*copied")
            
            for line in iter(process.stdout.readline, ''):
                self.update_log(line.strip())
                match = progress_re.search(line)
                if match:
                    copied = int(match.group(1))
                    self.progress["value"] = copied
                    percent = (copied / total_size) * 100
                    self.status_label.config(text=f"Progress: {percent:.1f}%")
            
            process.wait()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)
                
            # Compute hash
            self.status_label.config(text="Computing hash...")
            hash_value = compute_hash(output_file, sd["hash_algorithm"])
            if hash_value:
                sd["hash_value"] = hash_value
                self.update_log(f"Hash computed: {hash_value}")
                self.next_btn.config(state="normal")
            else:
                raise Exception("Hash computation failed")

        except Exception as e:
            self.update_log(f"Acquisition failed: {str(e)}")
            messagebox.showerror("Error", f"Acquisition failed: {str(e)}")

    def update_log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def cancel(self):
        if messagebox.askyesno("Cancel", "Abort current acquisition?"):
            self.ctrl.show_frame("DeviceSelectionPage")

    def next_step(self):
        self.ctrl.show_frame("CompletionPage")

class CompletionPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.ctrl = controller
        ttk.Label(self, text="Acquisition Complete", font=("Helvetica", 18)).pack(pady=20)
        
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=20, pady=10)
        
        ttk.Label(content, text="Results Summary:").pack(anchor="w")
        self.summary = ttk.Text(content, height=8, state="normal")
        self.summary.pack(fill="both", expand=True, pady=10)
        
        btn_frame = ttk.Frame(content)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Generate Report", bootstyle="primary",
                 command=self.generate_report).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="New Acquisition", bootstyle="secondary",
                 command=self.new_acquisition).pack(side="right", padx=5)

    def generate_report(self):
        sd = self.ctrl.shared
        try:
            device_info = get_device_info(sd["device"])
            usb_info = get_usb_details()
            deleted_count = count_deleted_files(sd["image_file"], 
                                              detect_filesystem_type(sd["device"]))
            
            report_path = generate_html_report(sd, device_info, 
                                              deleted_count, usb_info)
            if report_path:
                self.summary.insert("end", f"Report generated: {report_path}\n")
                subprocess.Popen(["xdg-open", report_path])
            else:
                self.summary.insert("end", "Failed to generate report\n")
        except Exception as e:
            self.summary.insert("end", f"Report generation error: {str(e)}\n")

    def new_acquisition(self):
        self.ctrl.shared = {
            "case_id": "", "investigator": "", "notes": "",
            "device": "", "imaging_method": "", "output_format": "",
            "hash_algorithm": "", "save_path": "", "block_size": "4M",
            "threading_option": True, "bad_sectors_option": True,
            "image_file": "", "hash_value": "", "status": ""
        }
        self.ctrl.show_frame("CaseInfoPage")

# ----------------------
# Main Execution
# ----------------------
if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        logger.exception("Fatal error in main loop")
        messagebox.showerror("Fatal Error", f"Critical application failure: {str(e)}")