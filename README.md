# DiskBerry — Raspberry Pi Digital Forensic Acquisition Tool

> **Portable, touch‑friendly imaging appliance for investigators and students**
![DiskBerry UI](https://github.com/user-attachments/assets/b91e81cc-5566-4d62-a19d-5ab24412df59)

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#)
[![License](https://img.shields.io/badge/license-MIT-green)](#)

DiskBerry turns a Raspberry Pi 4 B (8 GB) into a field‑ready disk‑imaging station.  
It preserves evidence integrity through dual‑hash verification, supports both raw (`.img`) and AFF formats, and auto‑generates HTML reports.

---

## ✨ Key Features

| Capability            | Details                                                                                       |
|-----------------------|------------------------------------------------------------------------------------------------|
| **Full‑disk imaging** | Raw `.img` **or** AFF                                                                          |
| **Hash validation**   | Dual‑phase SHA‑256 / MD5 with mismatch alerts                                                  |
| **GUI workflow**      | 5‑step wizard (case info → device → options → progress → summary) optimized for touchscreen    |
| **Real‑time logging** | Rotating log files (`disk_tool_YYYYMMDD_HHMMSS.log`)                                           |
| **HTML reporting**    | One‑click report with USB descriptors & deleted‑file counts                                    |
| **Cross‑platform**    | Designed for Pi OS / Linux; read‑only mode works on Windows                                    |

---

## 🖥️ Hardware Requirements

* **Raspberry Pi 4 Model B** (8 GB recommended)  
* **Official 7‑inch HDMI touchscreen**  
* **256 GB USB 3.0 flash drive** (target image storage)  
* **GeeekPi active‑cooling case**  
* **5 V 3 A USB‑C power supply** (e.g., Anker 337 Power Bank for field use)

---

## 🛠️ Software Requirements

### Python packages (`pip install -r requirements.txt`)

| Package | Purpose |
|---------|---------|
| `ttkbootstrap` | Modern themed Tk/Ttk GUI |
| `pywin32` *(Windows only)* | USB enumeration via `win32com` |

### System binaries — Linux / Raspberry Pi OS

| Tool | Purpose |
|------|---------|
| `dd` | Raw imaging |
| `dcfldd`, `affconvert` | AFF imaging pipeline |
| `lsblk`, `blockdev`, `file` | Device info & filesystem detection |
| `fls` (Sleuth Kit) | Deleted‑file enumeration |
| `udevadm`, `lsusb` | USB metadata |
| `xdg-open` | Opens HTML report |
| `wmic` (Windows) | Device info on Windows |

---

## 🚀 Quick Start

```bash
# clone & create venv
git clone https://github.com/your‑handle/diskberry.git
cd diskberry
python3 -m venv .venv && source .venv/bin/activate

# install Python deps
pip install -r requirements.txt

# install system tools (Debian / Raspberry Pi OS)
sudo apt update && sudo apt install dcfldd afflib-tools sleuthkit \
     coreutils udev usbutils -y

# run (sudo needed for raw‑disk access)
sudo python3 diskberry.py
```

## Sample Report 
![DiskBerryReport](https://github.com/user-attachments/assets/422637f9-d93d-4bcb-bb58-a0ab9b133b3d)


