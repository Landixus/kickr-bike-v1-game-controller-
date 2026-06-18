#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
POTATO POC - Standalone Version
Reads Wahoo/KICKR Bike BLE data and maps it to an Xbox controller.
Configuration is loaded from device.ini next to this script.
"""

import asyncio
import configparser
import ctypes
import math
import os
import subprocess
import sys
import threading
import tkinter as tk
from ctypes import wintypes

import keyboard
import vgamepad
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from vgamepad import DS4_BUTTONS, DS4_DPAD_DIRECTIONS, XUSB_BUTTON


CPM_UUID = "00002a63-0000-1000-8000-00805f9b34fb"
INDOOR_BIKE_DATA_UUID = "00002ad2-0000-1000-8000-00805f9b34fb"
HEART_RATE_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
WAHOO_BUTTON_UUID = "a026e03c-0a7d-4ab3-97fa-f1500f9feb8b"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "device.ini")
BRIDGE_EXE = os.path.join(BASE_DIR, "bridge", "ViGEmX360Bridge.exe")
KEYBOARD_BRIDGE_EXE = os.path.join(BASE_DIR, "keyboard", "KeyboardBridge.exe")

DEFAULT_BUTTON_MAPPINGS = {
    # Hood buttons: left/right -> A/X
    "20-00-0C": ("A", "Left inner hood button"),
    "00-08-11": ("X", "Right inner hood button"),

    # Top handlebar buttons -> D-Pad
    "02-00-01": ("DPAD_LEFT", "Left top front"),
    "04-00-01": ("DPAD_DOWN", "Left top rear"),
    "00-01-01": ("DPAD_UP", "Right top front"),
    "80-00-01": ("DPAD_RIGHT", "Right top rear"),

    # Outer shifters -> shoulders
    "10-00-01": ("LB", "Left outer shifter front"),
    "08-00-01": ("LB", "Left outer shifter rear"),
    "00-04-01": ("RB", "Right outer shifter front"),
    "00-02-01": ("RB", "Right outer shifter rear"),

    # Brakes -> B
    "01-00-01": ("B", "Left brake"),
    "40-00-01": ("B", "Right brake"),
}

DEFAULT_AXIS_MAPPINGS = {
    "20-00-0C": "LX_NEG",
    "00-08-11": "LX_POS",
    "02-00-01": "LY_POS",
    "04-00-01": "LY_NEG",
    "00-01-01": "RY_POS",
    "80-00-01": "RY_NEG",
    "10-00-01": "LX_NEG",
    "08-00-01": "LY_NEG",
    "00-04-01": "LX_POS",
    "00-02-01": "LY_POS",
    "01-00-01": "LT",
    "40-00-01": "LT",
}

DEFAULT_KEY_MAPPINGS = {
    "20-00-0C": "a",
    "00-08-11": "d",
    "02-00-01": "w",
    "04-00-01": "s",
    "00-01-01": "w",
    "80-00-01": "s",
    "10-00-01": "a",
    "08-00-01": "s",
    "00-04-01": "d",
    "00-02-01": "w",
    "01-00-01": "s",
    "40-00-01": "s",
}

DS4_BUTTON_MAP = {
    "A": DS4_BUTTONS.DS4_BUTTON_CROSS,
    "B": DS4_BUTTONS.DS4_BUTTON_CIRCLE,
    "X": DS4_BUTTONS.DS4_BUTTON_SQUARE,
    "Y": DS4_BUTTONS.DS4_BUTTON_TRIANGLE,
    "LB": DS4_BUTTONS.DS4_BUTTON_SHOULDER_LEFT,
    "RB": DS4_BUTTONS.DS4_BUTTON_SHOULDER_RIGHT,
}

VIRTUAL_KEYS = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10, "ctrl": 0x11,
    "alt": 0x12, "escape": 0x1B, "space": 0x20,
    "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46,
    "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52,
    "s": 0x53, "t": 0x54, "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
    "y": 0x59, "z": 0x5A,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "f13": 0x7C, "f14": 0x7D, "f15": 0x7E, "f16": 0x7F, "f17": 0x80, "f18": 0x81,
    "f19": 0x82, "f20": 0x83, "f21": 0x84, "f22": 0x85, "f23": 0x86, "f24": 0x87,
}

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    )


class INPUTUNION(ctypes.Union):
    _fields_ = (("ki", KEYBDINPUT),)


class INPUT(ctypes.Structure):
    _fields_ = (
        ("type", wintypes.DWORD),
        ("union", INPUTUNION),
    )


GAMEPAD_BUTTONS = {
    "A": XUSB_BUTTON.XUSB_GAMEPAD_A,
    "B": XUSB_BUTTON.XUSB_GAMEPAD_B,
    "X": XUSB_BUTTON.XUSB_GAMEPAD_X,
    "Y": XUSB_BUTTON.XUSB_GAMEPAD_Y,
    "LB": XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    "RB": XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "DPAD_UP": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
    "DPAD_DOWN": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
    "DPAD_LEFT": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
    "DPAD_RIGHT": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
}


def load_or_create_config():
    config = configparser.ConfigParser()

    if not os.path.exists(CONFIG_FILE):
        config["SETTINGS"] = {
            "FTP": "230.0",
            "DeviceName": "KICKR",
            "HeartRateDeviceName": "",
            "Threshold": "0.0",
            "EnableGUI": "True",
            "EnableDPad": "False",
            "EnableBikeButtons": "True",
            "VirtualControllerType": "X360",
            "UseDotNetX360Bridge": "True",
            "BikeButtonOutputMode": "button",
            "EnableKeyboardFallback": "False",
            "EnableHeartRate": "False",
            "WindowOpacity": "1.0",
            "MinBikeButtonPressSeconds": "0.0",
            "ScanSeconds": "12.0",
            "RetryDelaySeconds": "3.0",
            "MaxScanAttempts": "0",
        }
        config["BUTTONS"] = {
            code: mapping for code, (mapping, _description) in DEFAULT_BUTTON_MAPPINGS.items()
        }
        config["AXES"] = dict(DEFAULT_AXIS_MAPPINGS)
        config["KEYS"] = dict(DEFAULT_KEY_MAPPINGS)
        with open(CONFIG_FILE, "w", encoding="utf-8") as configfile:
            config.write(configfile)

    config.read(CONFIG_FILE, encoding="utf-8")

    changed = False
    if "SETTINGS" not in config:
        config["SETTINGS"] = {}
        changed = True

    defaults = {
        "EnableBikeButtons": "True",
        "VirtualControllerType": "X360",
        "UseDotNetX360Bridge": "True",
        "BikeButtonOutputMode": "button",
        "EnableKeyboardFallback": "False",
        "EnableHeartRate": "False",
        "HeartRateDeviceName": "",
        "WindowOpacity": "1.0",
        "MinBikeButtonPressSeconds": "0.0",
        "ScanSeconds": "12.0",
        "RetryDelaySeconds": "3.0",
        "MaxScanAttempts": "0",
    }
    for key, value in defaults.items():
        if key not in config["SETTINGS"]:
            config["SETTINGS"][key] = value
            changed = True

    if "BUTTONS" not in config:
        config["BUTTONS"] = {}
        changed = True
    if "AXES" not in config:
        config["AXES"] = {}
        changed = True
    if "KEYS" not in config:
        config["KEYS"] = {}
        changed = True

    for code, (mapping, _description) in DEFAULT_BUTTON_MAPPINGS.items():
        if code not in config["BUTTONS"]:
            config["BUTTONS"][code] = mapping
            changed = True
    for code, mapping in DEFAULT_AXIS_MAPPINGS.items():
        if code not in config["AXES"]:
            config["AXES"][code] = mapping
            changed = True
    for code, mapping in DEFAULT_KEY_MAPPINGS.items():
        if code not in config["KEYS"]:
            config["KEYS"][code] = mapping
            changed = True

    if changed:
        with open(CONFIG_FILE, "w", encoding="utf-8") as configfile:
            config.write(configfile)

    return config


def normalize_uuid(value):
    return (value or "").strip("{}").lower()


def read_uint16(data, offset):
    return int.from_bytes(data[offset:offset + 2], byteorder="little", signed=False)


def read_int16(data, offset):
    return int.from_bytes(data[offset:offset + 2], byteorder="little", signed=True)


def has_bytes(data, offset, count):
    return offset >= 0 and count >= 0 and offset + count <= len(data)


def parse_cycling_power(data):
    if len(data) < 4:
        return {}

    result = {"power": read_int16(data, 2)}
    flags = read_uint16(data, 0)
    offset = 4

    if flags & (1 << 0):
        offset += 1
    if flags & (1 << 1):
        offset += 1
    if flags & (1 << 2):
        offset += 2
    if flags & (1 << 3):
        offset += 2
    if flags & (1 << 4):
        offset += 4
    if flags & (1 << 5) and has_bytes(data, offset, 4):
        result["crank_revolutions"] = read_uint16(data, offset)
        result["crank_event_time"] = read_uint16(data, offset + 2)

    return result


def parse_indoor_bike_data(data):
    if len(data) < 2:
        return {}

    result = {}
    flags = read_uint16(data, 0)
    offset = 2

    if (flags & (1 << 0)) == 0 and has_bytes(data, offset, 2):
        result["speed"] = read_uint16(data, offset) / 100.0
        offset += 2
    if flags & (1 << 1) and has_bytes(data, offset, 2):
        offset += 2
    if flags & (1 << 2) and has_bytes(data, offset, 2):
        result["cadence"] = read_uint16(data, offset) / 2.0
        offset += 2
    if flags & (1 << 3) and has_bytes(data, offset, 2):
        offset += 2
    if flags & (1 << 4) and has_bytes(data, offset, 3):
        offset += 3
    if flags & (1 << 5) and has_bytes(data, offset, 2):
        offset += 2
    if flags & (1 << 6) and has_bytes(data, offset, 2):
        result["power"] = read_int16(data, offset)
        offset += 2
    if flags & (1 << 7) and has_bytes(data, offset, 2):
        offset += 2
    if flags & (1 << 8) and has_bytes(data, offset, 5):
        offset += 5
    if flags & (1 << 9) and has_bytes(data, offset, 1):
        result["heart_rate"] = data[offset]

    return result


def parse_heart_rate(data):
    if len(data) < 2:
        return {}

    if data[0] & 0x01 and len(data) >= 3:
        return {"heart_rate": read_uint16(data, 1)}
    return {"heart_rate": data[1]}


def delta16(current, previous):
    return current - previous if current >= previous else current + 65536 - previous


class RealtimeData:
    def __init__(self):
        self.power = 0
        self.trigger = 0.0
        self.speed = None
        self.cadence = None
        self.heart_rate = None
        self.last_button = "-"


class KickrController:
    def __init__(self, ftp, device_name, threshold, scan_seconds, retry_delay_seconds,
                 max_scan_attempts, enable_bike_buttons, enable_heart_rate,
                 heart_rate_device_name, min_bike_button_press_seconds,
                 bike_button_output_mode, virtual_controller_type,
                 use_dotnet_x360_bridge, enable_keyboard_fallback,
                 button_mappings, axis_mappings, key_mappings,
                 update_callback, status_callback):
        self.ftp = ftp
        self.device_name = device_name.strip().upper()
        self.heart_rate_device_name = heart_rate_device_name.strip().upper()
        self.threshold = threshold
        self.scan_seconds = scan_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.max_scan_attempts = max_scan_attempts
        self.enable_bike_buttons = enable_bike_buttons
        self.enable_heart_rate = enable_heart_rate
        self.min_bike_button_press_seconds = min_bike_button_press_seconds
        self.bike_button_output_mode = bike_button_output_mode.strip().lower()
        self.virtual_controller_type = virtual_controller_type.strip().upper()
        self.use_dotnet_x360_bridge = use_dotnet_x360_bridge
        self.enable_keyboard_fallback = enable_keyboard_fallback
        self.button_mappings = button_mappings
        self.axis_mappings = axis_mappings
        self.key_mappings = key_mappings
        self.client = None
        self.heart_rate_client = None
        self.update_callback = update_callback
        self.status_callback = status_callback
        self.bridge_process = None
        self.keyboard_bridge_process = None
        if use_dotnet_x360_bridge:
            self.gamepad = None
        elif self.virtual_controller_type == "DS4":
            self.gamepad = vgamepad.VDS4Gamepad()
        else:
            self.gamepad = vgamepad.VX360Gamepad()
        self.ds4_gamepad = self.gamepad if self.virtual_controller_type == "DS4" else None
        self.data = RealtimeData()
        self._scan_attempt = 0
        self._pressed_buttons = {}
        self._active_button_counts = {}
        self._pending_button_releases = {}
        self._active_axis_counts = {}
        self._pending_axis_releases = {}
        self._pressed_keys = {}
        self._last_crank_revolutions = None
        self._last_crank_event_time = None
        self._ble_scan_lock = asyncio.Lock()
        if self.use_dotnet_x360_bridge:
            self.start_x360_bridge()

    def start_x360_bridge(self):
        if not os.path.exists(BRIDGE_EXE):
            self.status_callback(f"X360 bridge missing: {BRIDGE_EXE}")
            return

        try:
            self.bridge_process = subprocess.Popen(
                [BRIDGE_EXE],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            self.status_callback("X360 .NET bridge started")
        except Exception as exc:
            self.bridge_process = None
            self.status_callback(f"X360 bridge start failed: {exc}")

    def send_bridge(self, command):
        if not self.bridge_process or self.bridge_process.poll() is not None or not self.bridge_process.stdin:
            if self.use_dotnet_x360_bridge:
                self.start_x360_bridge()
            if not self.bridge_process or not self.bridge_process.stdin:
                return False

        try:
            self.bridge_process.stdin.write(command + "\n")
            self.bridge_process.stdin.flush()
            return True
        except Exception as exc:
            self.status_callback(f"X360 bridge command failed: {exc}")
            return False

    def start_keyboard_bridge(self):
        if not os.path.exists(KEYBOARD_BRIDGE_EXE):
            self.status_callback(f"Keyboard bridge missing: {KEYBOARD_BRIDGE_EXE}")
            return

        try:
            self.keyboard_bridge_process = subprocess.Popen(
                [KEYBOARD_BRIDGE_EXE],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            self.status_callback("Keyboard bridge started")
        except Exception as exc:
            self.keyboard_bridge_process = None
            self.status_callback(f"Keyboard bridge start failed: {exc}")

    def send_keyboard_bridge(self, key_name, pressed):
        if not self.keyboard_bridge_process or self.keyboard_bridge_process.poll() is not None or not self.keyboard_bridge_process.stdin:
            self.start_keyboard_bridge()
            if not self.keyboard_bridge_process or not self.keyboard_bridge_process.stdin:
                return False

        try:
            state = "down" if pressed else "up"
            self.keyboard_bridge_process.stdin.write(f"key {key_name} {state}\n")
            self.keyboard_bridge_process.stdin.flush()
            return True
        except Exception as exc:
            self.status_callback(f"Keyboard bridge command failed: {exc}")
            return False

    async def connect_with_retries(self):
        self._scan_attempt += 1
        suffix = f" ({self._scan_attempt}/{self.max_scan_attempts})" if self.max_scan_attempts > 0 else ""
        message = f"Searching BLE device containing '{self.device_name}'{suffix}..."
        print(message)
        self.status_callback(message)

        try:
            async with self._ble_scan_lock:
                devices = await asyncio.wait_for(
                    BleakScanner.discover(timeout=self.scan_seconds),
                    timeout=self.scan_seconds + 2,
                )
        except asyncio.TimeoutError:
            self.status_callback("BLE scan timeout.")
            return False
        except Exception as exc:
            self.status_callback(f"BLE scan error: {exc}")
            return False

        device = next((d for d in devices if d.name and self.device_name in d.name.upper()), None)
        if not device:
            self.status_callback(f"No device found: {self.device_name}")
            return False

        self.status_callback(f"Found {device.name}. Connecting...")
        self.client = BleakClient(device.address)

        try:
            await self.client.connect()
            self._scan_attempt = 0
            self.status_callback(f"Connected: {device.name}")
            return True
        except Exception as exc:
            self.client = None
            self.status_callback(f"Connection error: {exc}")
            return False

    async def start_notifications(self):
        subscribed = []
        for uuid, handler, label in (
            (CPM_UUID, self.handle_power_notify, "power"),
            (INDOOR_BIKE_DATA_UUID, self.handle_indoor_bike_notify, "bike data"),
            (WAHOO_BUTTON_UUID, self.handle_button_notify, "bike buttons"),
        ):
            if label == "bike buttons" and not self.enable_bike_buttons:
                continue
            if await self.try_start_notify(uuid, handler, label):
                subscribed.append(label)

        if "power" not in subscribed and "bike data" not in subscribed:
            self.status_callback("No power/bike data notification found.")
            return False

        self.status_callback("Receiving: " + ", ".join(subscribed))
        return True

    async def try_start_notify(self, uuid, handler, label):
        try:
            await self.client.start_notify(uuid, handler)
            print(f"Subscribed to {label}.")
            return True
        except (BleakError, Exception) as exc:
            print(f"Could not subscribe to {label}: {exc}")
            return False

    async def run_heart_rate(self):
        while True:
            if not self.enable_heart_rate or not self.heart_rate_device_name:
                await asyncio.sleep(self.retry_delay_seconds)
                continue

            client = await self.connect_heart_rate_belt()
            if not client:
                await asyncio.sleep(self.retry_delay_seconds)
                continue

            self.heart_rate_client = client
            try:
                await client.start_notify(HEART_RATE_UUID, self.handle_heart_rate_notify)
                self.status_callback("Heart-rate belt connected.")
                while client.is_connected:
                    await asyncio.sleep(1)
            except Exception as exc:
                print(f"Heart-rate error: {exc}")
                self.status_callback(f"Heart-rate error: {exc}")
            finally:
                try:
                    if client.is_connected:
                        await client.disconnect()
                except Exception:
                    pass
                self.heart_rate_client = None
                self.status_callback("Heart-rate belt disconnected. Searching...")
                await asyncio.sleep(self.retry_delay_seconds)

    async def connect_heart_rate_belt(self):
        message = f"Searching HR belt containing '{self.heart_rate_device_name}'..."
        print(message)
        self.status_callback(message)

        try:
            async with self._ble_scan_lock:
                devices = await asyncio.wait_for(
                    BleakScanner.discover(timeout=self.scan_seconds),
                    timeout=self.scan_seconds + 2,
                )
        except Exception as exc:
            print(f"Heart-rate scan error: {exc}")
            self.status_callback(f"Heart-rate scan error: {exc}")
            return None

        device = next(
            (d for d in devices if d.name and self.heart_rate_device_name in d.name.upper()),
            None,
        )
        if not device:
            print(f"No heart-rate belt found: {self.heart_rate_device_name}")
            self.status_callback(f"HR belt not found: {self.heart_rate_device_name}")
            return None

        self.status_callback(f"Found HR belt: {device.name}. Connecting...")
        client = BleakClient(device.address)
        try:
            await client.connect()
            return client
        except Exception as exc:
            print(f"Heart-rate connection error: {exc}")
            self.status_callback(f"Heart-rate connection error: {exc}")
            return None

    async def scan_heart_rate_devices(self, result_callback):
        self.status_callback("Scanning BLE devices for heart-rate selection...")
        try:
            async with self._ble_scan_lock:
                devices = await asyncio.wait_for(
                    BleakScanner.discover(timeout=self.scan_seconds),
                    timeout=self.scan_seconds + 2,
                )
        except Exception as exc:
            self.status_callback(f"Heart-rate device scan error: {exc}")
            result_callback([])
            return

        found = []
        seen = set()
        for device in devices:
            name = (device.name or "").strip()
            if not name:
                continue
            key = (name.upper(), device.address)
            if key in seen:
                continue
            seen.add(key)
            found.append({"name": name, "address": device.address})

        found.sort(key=lambda item: item["name"].upper())
        self.status_callback(f"Found {len(found)} named BLE device(s).")
        result_callback(found)

    async def select_heart_rate_device(self, device_name):
        device_name = (device_name or "").strip()
        if not device_name:
            return

        self.heart_rate_device_name = device_name.upper()
        self.enable_heart_rate = True
        save_heart_rate_config(device_name, True)
        self.status_callback(f"Heart-rate device selected: {device_name}")

        if self.heart_rate_client and self.heart_rate_client.is_connected:
            try:
                await self.heart_rate_client.disconnect()
            except Exception as exc:
                print(f"Heart-rate disconnect before reconnect failed: {exc}")

    async def handle_power_notify(self, _sender, data):
        values = parse_cycling_power(data)
        self.apply_values(values)

    async def handle_indoor_bike_notify(self, _sender, data):
        self.apply_values(parse_indoor_bike_data(data))

    async def handle_heart_rate_notify(self, _sender, data):
        self.apply_values(parse_heart_rate(data))

    async def handle_button_notify(self, _sender, data):
        button_code, pressed = self.decode_wahoo_button(data)
        if not button_code:
            return

        was_pressed = self._pressed_buttons.get(button_code)
        if was_pressed == pressed:
            return
        self._pressed_buttons[button_code] = pressed

        key_target = resolve_wahoo_mapping(self.key_mappings, button_code)
        use_keyboard_mapping = (
            (self.enable_keyboard_fallback or self.bike_button_output_mode == "keyboard")
            and key_target
        )

        if use_keyboard_mapping or self.bike_button_output_mode == "keyboard":
            target = None
        else:
            target = (
                resolve_wahoo_mapping(self.axis_mappings, button_code)
                if self.bike_button_output_mode == "axis"
                else resolve_wahoo_mapping(self.button_mappings, button_code)
            )
        self.data.last_button = f"{button_code} {'down' if pressed else 'up'}"

        if use_keyboard_mapping:
            self.set_keyboard_key(key_target, pressed)
            self.data.last_button += f" -> key:{key_target}"
        elif target:
            if self.bike_button_output_mode == "axis":
                if pressed:
                    self.press_gamepad_axis(target)
                else:
                    asyncio.create_task(self.release_gamepad_axis_after_delay(target))
            else:
                if pressed:
                    self.press_gamepad_button(target)
                else:
                    asyncio.create_task(self.release_gamepad_button_after_delay(target))
            self.data.last_button += f" -> {target}"
        else:
            print(f"Unmapped Wahoo button: {button_code}")

        self.emit_update()

    def apply_values(self, values):
        if "power" in values:
            self.data.power = values["power"]
            self.update_trigger()
        if "speed" in values:
            self.data.speed = values["speed"]
        if "cadence" in values:
            self.data.cadence = values["cadence"]
        if "heart_rate" in values:
            self.data.heart_rate = values["heart_rate"]
        if "crank_revolutions" in values and "crank_event_time" in values:
            self.update_cadence_from_crank(values["crank_revolutions"], values["crank_event_time"])

        self.emit_update()

    def update_trigger(self):
        if self.data.power < self.threshold:
            self.data.trigger = 0.0
        else:
            scale = math.atanh(0.75) / self.ftp
            self.data.trigger = math.tanh(scale * self.data.power)

        trigger_value = int(self.data.trigger * 255)
        if self.use_dotnet_x360_bridge:
            self.send_bridge(f"rt {trigger_value}")
        elif self.gamepad:
            self.gamepad.right_trigger(trigger_value)
            self.gamepad.update()

    def update_cadence_from_crank(self, revolutions, event_time):
        if self._last_crank_revolutions is not None and self._last_crank_event_time is not None:
            rev_delta = delta16(revolutions, self._last_crank_revolutions)
            time_delta = delta16(event_time, self._last_crank_event_time)
            if rev_delta > 0 and time_delta > 0:
                self.data.cadence = rev_delta * 60.0 * 1024.0 / time_delta

        self._last_crank_revolutions = revolutions
        self._last_crank_event_time = event_time

    def press_gamepad_button(self, button_name):
        button = self.resolve_gamepad_button(button_name)
        if not button:
            self.status_callback(f"Unknown gamepad button: {button_name}")
            return

        pending = self._pending_button_releases.pop(button, None)
        if pending:
            pending.cancel()

        count = self._active_button_counts.get(button, 0)
        try:
            if self.use_dotnet_x360_bridge:
                self.send_bridge(f"btn {button_name.upper()} down")
            elif count == 0:
                if self.virtual_controller_type == "DS4":
                    self.gamepad.press_button(button)
                    self.gamepad.update()
                elif self.gamepad:
                    self.gamepad.report.wButtons = int(self.gamepad.report.wButtons) | int(button)
                    self.gamepad.update()
            self._active_button_counts[button] = count + 1
            self.status_callback(f"Gamepad {button_name.upper()} down")
        except Exception as exc:
            self.status_callback(f"Gamepad button error: {exc}")

    async def release_gamepad_button_after_delay(self, button_name):
        button = self.resolve_gamepad_button(button_name)
        if not button:
            self.status_callback(f"Unknown gamepad button: {button_name}")
            return

        old_pending = self._pending_button_releases.pop(button, None)
        if old_pending:
            old_pending.cancel()

        task = asyncio.current_task()
        self._pending_button_releases[button] = task
        try:
            if self.min_bike_button_press_seconds > 0:
                await asyncio.sleep(self.min_bike_button_press_seconds)
            count = max(0, self._active_button_counts.get(button, 0) - 1)
            if count <= 0:
                if self.use_dotnet_x360_bridge:
                    self.send_bridge(f"btn {button_name.upper()} up")
                elif self.virtual_controller_type == "DS4":
                    self.gamepad.release_button(button)
                    self.gamepad.update()
                elif self.gamepad:
                    self.gamepad.report.wButtons = int(self.gamepad.report.wButtons) & ~int(button)
                self._active_button_counts.pop(button, None)
                self._pending_button_releases.pop(button, None)
            else:
                self._active_button_counts[button] = count
            if self.gamepad:
                self.gamepad.update()
            self.status_callback(f"Gamepad {button_name.upper()} up")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.status_callback(f"Gamepad release error: {exc}")

    def resolve_gamepad_button(self, button_name):
        name = button_name.upper()
        if self.virtual_controller_type == "DS4":
            return DS4_BUTTON_MAP.get(name)
        return GAMEPAD_BUTTONS.get(name)

    def press_gamepad_axis(self, axis_name):
        axis_name = axis_name.upper()
        pending = self._pending_axis_releases.pop(axis_name, None)
        if pending:
            pending.cancel()

        self._active_axis_counts[axis_name] = self._active_axis_counts.get(axis_name, 0) + 1
        if self.use_dotnet_x360_bridge:
            self.send_bridge(f"axis {axis_name} down")
        else:
            self.apply_gamepad_axes()
        self.status_callback(f"Gamepad axis {axis_name} down")

    async def release_gamepad_axis_after_delay(self, axis_name):
        axis_name = axis_name.upper()
        old_pending = self._pending_axis_releases.pop(axis_name, None)
        if old_pending:
            old_pending.cancel()

        task = asyncio.current_task()
        self._pending_axis_releases[axis_name] = task
        try:
            if self.min_bike_button_press_seconds > 0:
                await asyncio.sleep(self.min_bike_button_press_seconds)
            count = max(0, self._active_axis_counts.get(axis_name, 0) - 1)
            if count <= 0:
                self._active_axis_counts.pop(axis_name, None)
                self._pending_axis_releases.pop(axis_name, None)
            else:
                self._active_axis_counts[axis_name] = count
            if self.use_dotnet_x360_bridge:
                self.send_bridge(f"axis {axis_name} up")
            else:
                self.apply_gamepad_axes()
            self.status_callback(f"Gamepad axis {axis_name} up")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.status_callback(f"Gamepad axis release error: {exc}")

    def apply_gamepad_axes(self):
        lt = 255 if self._active_axis_counts.get("LT", 0) > 0 else 0

        try:
            if self.gamepad:
                if self.virtual_controller_type == "DS4":
                    lx = self.ds4_axis_value("LX_POS", "LX_NEG")
                    ly = self.ds4_axis_value("LY_NEG", "LY_POS")
                    rx = self.ds4_axis_value("RX_POS", "RX_NEG")
                    ry = self.ds4_axis_value("RY_NEG", "RY_POS")
                else:
                    lx = self.axis_value("LX_POS", "LX_NEG")
                    ly = self.axis_value("LY_POS", "LY_NEG")
                    rx = self.axis_value("RX_POS", "RX_NEG")
                    ry = self.axis_value("RY_POS", "RY_NEG")
                self.gamepad.left_joystick(lx, ly)
                self.gamepad.right_joystick(rx, ry)
                self.gamepad.left_trigger(lt)
                self.gamepad.update()
        except Exception as exc:
            self.status_callback(f"Gamepad axis error: {exc}")

    def axis_value(self, positive_name, negative_name):
        positive = self._active_axis_counts.get(positive_name, 0) > 0
        negative = self._active_axis_counts.get(negative_name, 0) > 0
        if positive and not negative:
            return 32767
        if negative and not positive:
            return -32768
        return 0

    def ds4_axis_value(self, positive_name, negative_name):
        positive = self._active_axis_counts.get(positive_name, 0) > 0
        negative = self._active_axis_counts.get(negative_name, 0) > 0
        if positive and not negative:
            return 255
        if negative and not positive:
            return 0
        return 128

    def set_keyboard_key(self, key_name, pressed):
        key_name = key_name.strip().lower()
        if not key_name or key_name == "off":
            return

        virtual_key = VIRTUAL_KEYS.get(key_name)
        if not virtual_key:
            self.status_callback(f"Unknown keyboard key: {key_name}")
            return

        try:
            if pressed:
                if not self._pressed_keys.get(key_name, False):
                    self.send_keyboard_output(key_name, virtual_key, True)
                    self._pressed_keys[key_name] = True
                self.status_callback(f"Keyboard {key_name} down")
            else:
                if self._pressed_keys.get(key_name, False):
                    self.send_keyboard_output(key_name, virtual_key, False)
                    self._pressed_keys[key_name] = False
                self.status_callback(f"Keyboard {key_name} up")
        except Exception as exc:
            self.status_callback(f"Keyboard output error: {exc}")

    def send_keyboard_output(self, key_name, virtual_key, pressed):
        try:
            self.send_virtual_key(virtual_key, pressed, use_scancode=True)
        except Exception:
            self.send_keybd_event(virtual_key, pressed)

    @staticmethod
    def send_virtual_key(virtual_key, pressed, use_scancode=True):
        flags = 0
        if not pressed:
            flags |= KEYEVENTF_KEYUP
        if use_scancode:
            scan_code = ctypes.windll.user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
            flags |= KEYEVENTF_SCANCODE
            w_vk = 0
        else:
            scan_code = 0
            w_vk = virtual_key
        input_event = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUTUNION(ki=KEYBDINPUT(
                wVk=w_vk,
                wScan=scan_code,
                dwFlags=flags,
                time=0,
                dwExtraInfo=None,
            )),
        )
        sent = ctypes.windll.user32.SendInput(1, ctypes.byref(input_event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError()

    @staticmethod
    def send_keybd_event(virtual_key, pressed):
        scan_code = ctypes.windll.user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
        flags = 0 if pressed else KEYEVENTF_KEYUP
        ctypes.windll.user32.keybd_event(virtual_key, scan_code, flags, 0)

    async def run_keyboard_self_test(self):
        for seconds in (3, 2, 1):
            self.status_callback(f"Keyboard test in {seconds}s. Focus Notepad now.")
            await asyncio.sleep(1)

        await self.type_test_text("VK SendInput: ", use_scancode=False, use_keybd_event=False)
        await asyncio.sleep(0.7)
        await self.type_test_text(" SC SendInput: ", use_scancode=True, use_keybd_event=False)
        await asyncio.sleep(0.7)
        await self.type_test_text(" keybd_event: ", use_scancode=False, use_keybd_event=True)
        self.status_callback("Keyboard self-test finished")

    async def run_ds4_self_test(self):
        self.status_callback("Creating DS4 test controller...")
        try:
            if self.ds4_gamepad is None:
                self.ds4_gamepad = vgamepad.VDS4Gamepad()
            ds4 = self.ds4_gamepad
        except Exception as exc:
            self.status_callback(f"DS4 create failed: {exc}")
            return

        steps = [
            ("DS4 Cross", lambda: ds4.press_button(DS4_BUTTONS.DS4_BUTTON_CROSS),
             lambda: ds4.release_button(DS4_BUTTONS.DS4_BUTTON_CROSS)),
            ("DS4 Circle", lambda: ds4.press_button(DS4_BUTTONS.DS4_BUTTON_CIRCLE),
             lambda: ds4.release_button(DS4_BUTTONS.DS4_BUTTON_CIRCLE)),
            ("DS4 Square", lambda: ds4.press_button(DS4_BUTTONS.DS4_BUTTON_SQUARE),
             lambda: ds4.release_button(DS4_BUTTONS.DS4_BUTTON_SQUARE)),
            ("DS4 DPad North", lambda: ds4.directional_pad(DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTH),
             lambda: ds4.directional_pad(DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE)),
            ("DS4 left trigger", lambda: ds4.left_trigger(255),
             lambda: ds4.left_trigger(0)),
        ]

        for label, press, release in steps:
            self.status_callback(f"TEST: {label}")
            press()
            ds4.update()
            await asyncio.sleep(1.2)
            release()
            ds4.update()
            await asyncio.sleep(0.4)

        self.status_callback("DS4 self-test finished")

    async def type_test_text(self, label, use_scancode, use_keybd_event):
        self.status_callback(f"TEST:{label}abx")
        for ch in "abx":
            vk = VIRTUAL_KEYS[ch]
            if use_keybd_event:
                self.send_keybd_event(vk, True)
                await asyncio.sleep(0.05)
                self.send_keybd_event(vk, False)
            else:
                self.send_virtual_key(vk, True, use_scancode=use_scancode)
                await asyncio.sleep(0.05)
                self.send_virtual_key(vk, False, use_scancode=use_scancode)
            await asyncio.sleep(0.18)

    async def run_gamepad_self_test(self):
        for seconds in (3, 2, 1):
            self.status_callback(f"Gamepad self-test starts in {seconds}s. Focus Notepad/game now.")
            await asyncio.sleep(1)

        self.status_callback("Gamepad self-test started")
        await self.hold_test_state("left stick right", lx=32767)
        await self.hold_test_state("left stick left", lx=-32768)
        await self.hold_test_state("left stick up", ly=32767)
        await self.hold_test_state("left stick down", ly=-32768)
        await self.hold_test_state("right stick up", ry=32767)
        await self.hold_test_state("left trigger", lt=255)
        await self.hold_test_state("button A direct", buttons=int(XUSB_BUTTON.XUSB_GAMEPAD_A))
        await self.hold_test_state("button B direct", buttons=int(XUSB_BUTTON.XUSB_GAMEPAD_B))
        await self.hold_test_state("button X direct", buttons=int(XUSB_BUTTON.XUSB_GAMEPAD_X))
        await self.hold_test_state(
            "all face buttons direct",
            buttons=int(
                XUSB_BUTTON.XUSB_GAMEPAD_A |
                XUSB_BUTTON.XUSB_GAMEPAD_B |
                XUSB_BUTTON.XUSB_GAMEPAD_X |
                XUSB_BUTTON.XUSB_GAMEPAD_Y
            ),
        )
        self.status_callback("TEST: SendInput keyboard a/b/x")
        for key_name in ("a", "b", "x"):
            self.send_virtual_key(VIRTUAL_KEYS[key_name], True)
            await asyncio.sleep(0.08)
            self.send_virtual_key(VIRTUAL_KEYS[key_name], False)
            await asyncio.sleep(0.3)

        self.reset_test_controls()
        self.gamepad.update()
        self.status_callback("Gamepad self-test finished")

    async def hold_test_state(self, label, lx=0, ly=0, rx=0, ry=0, lt=0, buttons=0):
        self.status_callback(f"TEST: {label} buttons={buttons}")
        end_time = asyncio.get_running_loop().time() + 1.5
        while asyncio.get_running_loop().time() < end_time:
            self.gamepad.report.sThumbLX = lx
            self.gamepad.report.sThumbLY = ly
            self.gamepad.report.sThumbRX = rx
            self.gamepad.report.sThumbRY = ry
            self.gamepad.report.bLeftTrigger = lt
            self.gamepad.report.wButtons = buttons
            self.gamepad.update()
            await asyncio.sleep(0.05)

    def reset_test_controls(self):
        self.gamepad.left_joystick(0, 0)
        self.gamepad.right_joystick(0, 0)
        self.gamepad.left_trigger(0)
        self.gamepad.report.wButtons = 0
        for button in (
            XUSB_BUTTON.XUSB_GAMEPAD_A,
            XUSB_BUTTON.XUSB_GAMEPAD_B,
            XUSB_BUTTON.XUSB_GAMEPAD_X,
            XUSB_BUTTON.XUSB_GAMEPAD_Y,
            XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
            XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
            XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        ):
            self.gamepad.release_button(button)

    @staticmethod
    def decode_wahoo_button(packet):
        if packet is None or len(packet) != 3:
            return None, False

        raw = packet[2]
        code = f"{packet[0]:02X}-{packet[1]:02X}-{raw & 0x7F:02X}"
        if code == "00-00-00":
            return None, False

        return code, (raw & 0x80) != 0

    def emit_update(self):
        self.update_callback(self.data)

    async def run(self):
        while True:
            if self.max_scan_attempts > 0 and self._scan_attempt >= self.max_scan_attempts:
                self.status_callback("Max scan attempts reached.")
                return

            if not await self.connect_with_retries():
                await asyncio.sleep(self.retry_delay_seconds)
                continue

            if not await self.start_notifications():
                await self.disconnect()
                await asyncio.sleep(self.retry_delay_seconds)
                continue

            while self.client and self.client.is_connected:
                await asyncio.sleep(1)

            self.status_callback("Connection lost. Searching again...")
            await self.disconnect()
            await asyncio.sleep(self.retry_delay_seconds)

    async def disconnect(self):
        if self.client:
            try:
                if self.client.is_connected:
                    await self.client.disconnect()
            except Exception as exc:
                print(f"Disconnect error: {exc}")
            finally:
                self.client = None


def setup_keyboard_mapping(gamepad):
    key_map = {
        "left": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
        "right": XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        "home": XUSB_BUTTON.XUSB_GAMEPAD_A,
        "shift": XUSB_BUTTON.XUSB_GAMEPAD_B,
        "enter": XUSB_BUTTON.XUSB_GAMEPAD_X,
        "end": XUSB_BUTTON.XUSB_GAMEPAD_Y,
        "=": XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
        "subtract": XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    }

    try:
        for key, button in key_map.items():
            keyboard.on_press_key(key, lambda _e, b=button: (gamepad.press_button(b), gamepad.update()))
            keyboard.on_release_key(key, lambda _e, b=button: (gamepad.release_button(b), gamepad.update()))
    except Exception as exc:
        print(f"Could not load keyboard mapping: {exc}")


class MinimalGUI:
    def __init__(self, device_name, initial_opacity):
        self.root = tk.Tk()
        self.root.title(f"BLE Bridge - {device_name}")
        self.root.configure(bg="black")
        self.root.geometry("640x340")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.opacity = min(1.0, max(0.35, initial_opacity))
        self.root.attributes("-alpha", self.opacity)

        self.status_var = tk.StringVar(value="Waiting for connection...")
        self.opacity_var = tk.StringVar(value=f"{int(self.opacity * 100)}%")
        self.power_var = tk.StringVar(value="0 W")
        self.speed_var = tk.StringVar(value="- km/h")
        self.cadence_var = tk.StringVar(value="- rpm")
        self.heart_rate_var = tk.StringVar(value="- bpm")
        self.button_var = tk.StringVar(value="-")
        self.heart_rate_scan_callback = None
        self.heart_rate_select_callback = None
        self.gamepad_test_callback = None
        self.keyboard_test_callback = None
        self.ds4_test_callback = None

        top = tk.Frame(self.root, bg="black")
        top.pack(fill="x", padx=18, pady=(12, 4))

        self.status_label = tk.Label(top, textvariable=self.status_var, fg="white", bg="black",
                                     font=("Helvetica", 11, "bold"), anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)

        controls = tk.Frame(top, bg="black")
        controls.pack(side="right")
        tk.Button(controls, text="HR", width=4, command=self.request_heart_rate_scan,
                  bg="#222222", fg="white", activebackground="#333333",
                  activeforeground="white", relief="solid", bd=1).pack(side="left", padx=(2, 10))
        tk.Button(controls, text="-", width=3, command=lambda: self.adjust_opacity(-0.08),
                  bg="#222222", fg="white", activebackground="#333333",
                  activeforeground="white", relief="solid", bd=1).pack(side="left", padx=2)
        tk.Label(controls, textvariable=self.opacity_var, fg="white", bg="black",
                 font=("Helvetica", 10, "bold"), width=4).pack(side="left")
        tk.Button(controls, text="+", width=3, command=lambda: self.adjust_opacity(0.08),
                  bg="#222222", fg="white", activebackground="#333333",
                  activeforeground="white", relief="solid", bd=1).pack(side="left", padx=2)

        self.canvas = tk.Canvas(self.root, height=40, width=600, bg="black", highlightthickness=0)
        self.canvas.pack(pady=(16, 8))
        self.canvas.create_rectangle(0, 0, 600, 40, outline="white", fill="black", tags="bg")
        self.canvas.create_rectangle(0, 0, 0, 40, outline="", fill="lime", tags="bar")

        grid = tk.Frame(self.root, bg="black")
        grid.pack(pady=12)
        self.add_metric(grid, 0, 0, "POWER", self.power_var, "lime")
        self.add_metric(grid, 0, 1, "SPEED", self.speed_var, "cyan")
        self.add_metric(grid, 1, 0, "CADENCE", self.cadence_var, "orange")
        self.add_metric(grid, 1, 1, "HEARTRATE", self.heart_rate_var, "red")

        button_frame = tk.Frame(self.root, bg="#101010", width=600, height=44,
                                highlightbackground="#444444", highlightthickness=1)
        button_frame.pack(pady=(4, 0))
        button_frame.pack_propagate(False)
        tk.Label(button_frame, textvariable=self.button_var, fg="#ffeb66", bg="#101010",
                 font=("Consolas", 13, "bold"), wraplength=570).pack(expand=True)

    @staticmethod
    def add_metric(parent, row, column, label, variable, color):
        frame = tk.Frame(parent, bg="black", width=290, height=62)
        frame.grid(row=row, column=column, padx=12, pady=5)
        frame.grid_propagate(False)
        tk.Label(frame, text=label, fg="gray", bg="black", font=("Helvetica", 9, "bold")).pack()
        tk.Label(frame, textvariable=variable, fg=color, bg="black", font=("Helvetica", 24, "bold")).pack()

    def adjust_opacity(self, delta):
        self.opacity = min(1.0, max(0.35, self.opacity + delta))
        self.root.attributes("-alpha", self.opacity)
        self.opacity_var.set(f"{int(self.opacity * 100)}%")

    def set_heart_rate_callbacks(self, scan_callback, select_callback):
        self.heart_rate_scan_callback = scan_callback
        self.heart_rate_select_callback = select_callback

    def set_gamepad_test_callback(self, test_callback):
        self.gamepad_test_callback = test_callback

    def set_keyboard_test_callback(self, test_callback):
        self.keyboard_test_callback = test_callback

    def set_ds4_test_callback(self, test_callback):
        self.ds4_test_callback = test_callback

    def request_gamepad_test(self):
        if self.gamepad_test_callback:
            self.status_var.set("Starting gamepad self-test...")
            self.gamepad_test_callback()

    def request_keyboard_test(self):
        if self.keyboard_test_callback:
            self.status_var.set("Starting keyboard self-test...")
            self.keyboard_test_callback()

    def request_ds4_test(self):
        if self.ds4_test_callback:
            self.status_var.set("Starting DS4 self-test...")
            self.ds4_test_callback()

    def request_heart_rate_scan(self):
        if self.heart_rate_scan_callback:
            self.status_var.set("Scanning BLE devices...")
            self.heart_rate_scan_callback()

    def show_heart_rate_devices(self, devices):
        self.root.after(0, self._show_heart_rate_devices, devices)

    def _show_heart_rate_devices(self, devices):
        popup = tk.Toplevel(self.root)
        popup.title("Select Heart Rate Device")
        popup.configure(bg="black")
        popup.geometry("520x360")
        popup.attributes("-topmost", True)
        popup.transient(self.root)

        tk.Label(popup, text="Select heart-rate strap", fg="white", bg="black",
                 font=("Helvetica", 14, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        tk.Label(popup, text="All named BLE devices found in the scan are listed.",
                 fg="#aaaaaa", bg="black", font=("Helvetica", 9)).pack(anchor="w", padx=14)

        frame = tk.Frame(popup, bg="black")
        frame.pack(fill="both", expand=True, padx=14, pady=12)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
        listbox = tk.Listbox(frame, bg="#101010", fg="white", selectbackground="#2d6cdf",
                             selectforeground="white", font=("Consolas", 11),
                             yscrollcommand=scrollbar.set, activestyle="none")
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        if not devices:
            listbox.insert("end", "No named BLE devices found")
        else:
            for device in devices:
                listbox.insert("end", f"{device['name']}    {device['address']}")

        def select_current():
            if not devices:
                return
            selection = listbox.curselection()
            if not selection:
                return
            device = devices[selection[0]]
            if self.heart_rate_select_callback:
                self.heart_rate_select_callback(device["name"])
            self.heart_rate_var.set("connecting...")
            self.status_var.set(f"Selected HR: {device['name']}")
            popup.destroy()

        listbox.bind("<Double-Button-1>", lambda _event: select_current())

        buttons = tk.Frame(popup, bg="black")
        buttons.pack(fill="x", padx=14, pady=(0, 14))
        tk.Button(buttons, text="Connect", command=select_current, width=12,
                  bg="#2d6cdf", fg="white", activebackground="#3d7cef",
                  activeforeground="white", relief="solid", bd=1).pack(side="right", padx=(8, 0))
        tk.Button(buttons, text="Cancel", command=popup.destroy, width=10,
                  bg="#222222", fg="white", activebackground="#333333",
                  activeforeground="white", relief="solid", bd=1).pack(side="right")

    def update(self, data):
        self.root.after(0, self._update, data.power, data.trigger, data.speed,
                        data.cadence, data.heart_rate, data.last_button)

    def _update(self, power, trigger, speed, cadence, heart_rate, last_button):
        self.canvas.coords("bar", 0, 0, int(trigger * 600), 40)
        self.power_var.set(f"{power} W")
        self.speed_var.set(f"{speed:.1f} km/h" if speed is not None else "- km/h")
        self.cadence_var.set(f"{cadence:.0f} rpm" if cadence is not None else "- rpm")
        self.heart_rate_var.set(f"{heart_rate} bpm" if heart_rate is not None else "- bpm")
        self.button_var.set(f"Button: {last_button}")

    def update_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text[:80]))

    def run(self):
        self.root.mainloop()


def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def load_button_mappings(config):
    mappings = {}
    if "BUTTONS" not in config:
        return mappings

    for code, target in config["BUTTONS"].items():
        code = code.strip().upper()
        target = target.strip().upper()
        if target and target != "OFF":
            mappings[code] = target

    return mappings


def load_axis_mappings(config):
    mappings = {}
    if "AXES" not in config:
        return mappings

    for code, target in config["AXES"].items():
        code = code.strip().upper()
        target = target.strip().upper()
        if target and target != "OFF":
            mappings[code] = target

    return mappings


def load_key_mappings(config):
    mappings = {}
    if "KEYS" not in config:
        return mappings

    for code, target in config["KEYS"].items():
        code = code.strip().upper()
        target = target.strip()
        if target and target.lower() != "off":
            mappings[code] = target

    return mappings


def resolve_wahoo_mapping(mappings, button_code):
    direct = mappings.get(button_code)
    if direct:
        return direct

    parts = button_code.split("-")
    if len(parts) < 2:
        return None

    button_prefix = "-".join(parts[:2])
    for configured_code, target in mappings.items():
        configured_parts = configured_code.split("-")
        if len(configured_parts) >= 2 and "-".join(configured_parts[:2]) == button_prefix:
            return target

    return None


def save_heart_rate_config(device_name, enabled):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding="utf-8")
    if "SETTINGS" not in config:
        config["SETTINGS"] = {}

    config["SETTINGS"]["HeartRateDeviceName"] = device_name
    config["SETTINGS"]["EnableHeartRate"] = "True" if enabled else "False"

    with open(CONFIG_FILE, "w", encoding="utf-8") as configfile:
        config.write(configfile)


def main():
    config = load_or_create_config()

    try:
        settings = config["SETTINGS"]
        ftp = float(settings.get("FTP", 230.0))
        device_name = settings.get("DeviceName", "KICKR")
        heart_rate_device_name = settings.get("HeartRateDeviceName", "")
        threshold = float(settings.get("Threshold", 0.0))
        enable_gui = settings.getboolean("EnableGUI", True)
        enable_dpad = settings.getboolean("EnableDPad", True)
        enable_bike_buttons = settings.getboolean("EnableBikeButtons", True)
        virtual_controller_type = settings.get("VirtualControllerType", "DS4")
        use_dotnet_x360_bridge = settings.getboolean("UseDotNetX360Bridge", True)
        bike_button_output_mode = settings.get("BikeButtonOutputMode", "axis")
        enable_keyboard_fallback = settings.getboolean("EnableKeyboardFallback", True)
        enable_heart_rate = settings.getboolean("EnableHeartRate", False)
        window_opacity = float(settings.get("WindowOpacity", 1.0))
        min_bike_button_press_seconds = float(settings.get("MinBikeButtonPressSeconds", 0.18))
        scan_seconds = float(settings.get("ScanSeconds", 12.0))
        retry_delay_seconds = float(settings.get("RetryDelaySeconds", 3.0))
        max_scan_attempts = int(settings.get("MaxScanAttempts", 0))
    except ValueError as exc:
        print(f"Error in device.ini: {exc}")
        input("Press Enter to exit...")
        return

    gui = MinimalGUI(device_name, window_opacity) if enable_gui else None

    loop = asyncio.new_event_loop()
    threading.Thread(target=start_loop, args=(loop,), daemon=True).start()

    controller = KickrController(
        ftp=ftp,
        device_name=device_name,
        threshold=threshold,
        scan_seconds=scan_seconds,
        retry_delay_seconds=retry_delay_seconds,
        max_scan_attempts=max_scan_attempts,
        enable_bike_buttons=enable_bike_buttons,
        enable_heart_rate=enable_heart_rate,
        heart_rate_device_name=heart_rate_device_name,
        min_bike_button_press_seconds=min_bike_button_press_seconds,
        bike_button_output_mode=bike_button_output_mode,
        virtual_controller_type=virtual_controller_type,
        use_dotnet_x360_bridge=use_dotnet_x360_bridge,
        enable_keyboard_fallback=enable_keyboard_fallback,
        button_mappings=load_button_mappings(config),
        axis_mappings=load_axis_mappings(config),
        key_mappings=load_key_mappings(config),
        update_callback=(gui.update if gui else lambda d: print(
            f"{d.power} W | {d.speed} km/h | {d.cadence} rpm | {d.heart_rate} bpm"
        )),
        status_callback=(gui.update_status if gui else print),
    )

    if enable_dpad and controller.gamepad:
        setup_keyboard_mapping(controller.gamepad)

    if gui:
        gui.set_heart_rate_callbacks(
            scan_callback=lambda: asyncio.run_coroutine_threadsafe(
                controller.scan_heart_rate_devices(gui.show_heart_rate_devices), loop
            ),
            select_callback=lambda name: asyncio.run_coroutine_threadsafe(
                controller.select_heart_rate_device(name), loop
            ),
        )
        bridge = " .NET-X360" if use_dotnet_x360_bridge else f" {virtual_controller_type.upper()}"
        fallback = " + keyboard" if enable_keyboard_fallback else ""
        gui.update_status(f"Bike buttons: {bike_button_output_mode}{bridge}{fallback} | Config: {CONFIG_FILE}")

    asyncio.run_coroutine_threadsafe(controller.run(), loop)
    asyncio.run_coroutine_threadsafe(controller.run_heart_rate(), loop)

    if gui:
        gui.run()
    else:
        print("Press CTRL+C to exit.")
        keyboard.wait()


if __name__ == "__main__":
    main()
