# KICKR Game Controller

Use a Wahoo KICKR Bike as a virtual Xbox 360 controller for PC games.

The app reads power and button data from the bike over Bluetooth LE. Power is mapped to the controller trigger axis, and KICKR Bike buttons can be mapped to Xbox buttons, controller axes, or keyboard keys through `device.ini`.

## Download

Download the latest ready-to-use Windows build:

[quakeit.de/kickrGameController.zip](https://quakeit.de/kickrGameController.zip)

## Features

- Connects to a Wahoo KICKR Bike over Bluetooth LE
- Maps power output to a virtual Xbox 360 controller trigger
- Maps KICKR Bike buttons to Xbox buttons, D-pad, shoulders, trigger/axis controls, or keyboard keys
- Keeps buttons/keys held down until the physical bike button is released
- Optional heart-rate belt support
- Small always-on-top status window with power, speed, cadence, heart rate, button state, and opacity controls
- Configurable through `device.ini`

## Requirements

- Windows 10 or Windows 11
- Bluetooth LE support
- Wahoo KICKR Bike
- ViGEmBus installed for virtual Xbox 360 controller output

If the virtual Xbox controller does not appear, install ViGEmBus first. The included package may contain the installer:

`ViGEmBus_1.22.0_x64_x86_arm64.exe`

## Quick Start

1. Download and extract `kickrGameController.zip`.
2. Install ViGEmBus if it is not already installed.
3. Turn on the KICKR Bike.
4. Start `potatoNew.exe`.
5. Open the Windows game controller test panel to verify the Xbox 360 controller.
6. Start your game and bind the controller buttons as needed.

The app loads `device.ini` from the same folder as `potatoNew.exe`.

## Default Controller Setup

The default configuration uses a virtual Xbox 360 controller:

```ini
usedotnetx360bridge = True
bikebuttonoutputmode = button
enablekeyboardfallback = False
minbikebuttonpressseconds = 0.0
```

`minbikebuttonpressseconds = 0.0` means the virtual button stays pressed exactly as long as the KICKR Bike button is held.

## Button Mapping

KICKR Bike buttons are configured in `device.ini`.

Xbox button mapping:

```ini
[BUTTONS]
20-00-0C = A
00-08-11 = X
02-00-01 = DPAD_LEFT
04-00-01 = DPAD_DOWN
00-01-01 = DPAD_UP
80-00-01 = DPAD_RIGHT
10-00-01 = LB
08-00-01 = LB
00-04-01 = RB
00-02-01 = RB
01-00-01 = B
40-00-01 = B
```

The app matches Wahoo button codes by the first two bytes, so changing third-byte values from the bike are handled automatically.

## Keyboard Fallback

To use keyboard keys instead of Xbox buttons, set:

```ini
enablekeyboardfallback = True
```

Then edit the `[KEYS]` section:

```ini
[KEYS]
20-00-0C = a
00-08-11 = d
02-00-01 = w
04-00-01 = s
```

When keyboard fallback is enabled, the app uses `[KEYS]` instead of `[BUTTONS]` for KICKR Bike button output.

## Heart Rate Belt

Heart-rate support is optional:

```ini
enableheartrate = True
heartratedevicename = H9Z
```

You can also use the `HR` button in the app window to scan for nearby BLE devices and select a heart-rate strap.

## Troubleshooting

If the bike connects but buttons do not show on the Xbox controller:

- Make sure `usedotnetx360bridge = True`
- Make sure `bikebuttonoutputmode = button`
- Make sure `enablekeyboardfallback = False` if you want Xbox buttons
- Check that `bridge\ViGEmX360Bridge.exe` exists next to the app
- Confirm ViGEmBus is installed

If the bike is not found:

- Keep the bike awake
- Increase `scanseconds`
- Make sure no other app is already connected to the bike

If keyboard output is used:

- Set `enablekeyboardfallback = True`
- Configure keys in `[KEYS]`
- Run the target game and the app at the same privilege level if needed

## Configuration File

Common settings:

```ini
[SETTINGS]
ftp = 50.0
devicename = KICKR
threshold = 0.0
enablegui = True
enablebikebuttons = True
virtualcontrollertype = X360
usedotnetx360bridge = True
bikebuttonoutputmode = button
enablekeyboardfallback = False
enableheartrate = True
windowopacity = 1.0
minbikebuttonpressseconds = 0.0
scanseconds = 12.0
retrydelayseconds = 3.0
maxscanattempts = 0
```

## Notes

This is an experimental community tool for PC gaming with a Wahoo KICKR Bike. It is not an official Wahoo product.
