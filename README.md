<p align="center">
    <img width=200px height=200px src="lancet/icons/logo.png" alt="Project logo">
</p>

<p align="center">OCR application for reading manga in Japanese, made for AJATTers🇯🇵</p>

# Lancet

[![PyPi](https://img.shields.io/pypi/v/ajt-lancet?style=for-the-badge)](https://pypi.org/project/ajt-lancet/)
[![Chat](https://img.shields.io/badge/chat-join-green?style=for-the-badge&logo=Telegram&logoColor=green)](https://ajatt.top/blog/join-our-community.html)
[![Support](https://img.shields.io/badge/support-developer-orange?style=for-the-badge&logo=Patreon&logoColor=orange)](https://ajatt.top/blog/donating-to-tatsumoto.html)

Lancet is an OCR application for [reading manga in Japanese](https://ajatt.top/blog/mining-from-manga.html).
It uses PyTorch models to recognize Japanese text in images.
Lancet works best with [Goldendict-ng](https://xiaoyifang.github.io/goldendict-ng/)
or [Rikaitan](https://rikaitan.ajatt.top/).

https://github.com/user-attachments/assets/8859adac-1bd8-435a-9c81-945f875dc205

## User Guide

Prerequisites:

- [Goldendict](https://ajatt.top/blog/setting-up-goldendict.html) for looking up words in Japanese dictionaries.
- [nsxiv](https://wiki.archlinux.org/title/Sxiv) for reading manga.

Launch `Goldendict`, then open a manga folder in `nsxiv`.
Start `Lancet` and wait for the OCR model to load.
Press the OCR shortcut (default `Alt+O`) to show the snipping window,
then drag and hold the mouse to perform OCR.

Lancet adds an icon to the system tray.
Right‑click the icon to access actions, including Preferences,
where you can change the OCR shortcut.

## Installation

Install via [pipx](https://pipx.pypa.io/stable/) from [pypi](https://pypi.org/project/ajt-lancet/).

```bash
pipx install ajt-lancet
```

The `lancet` executable will be available in your `$PATH`.

On [Windows-like systems](https://reactos.org/),
you may need to add the folder containing the `lancet` executable to your `$PATH` manually.

### System Requirements

Lancet depends on large Python libraries.
`pipx` installs everything in an isolated location (`~/.local/share/pipx`)
so you can cleanly uninstall with `pipx uninstall` later.
The PyTorch models are downloaded from HuggingFace and saved to `~/.cache/huggingface`.

- Disk space: ~8 GiB (PyTorch and dependencies)
- RAM: at least 2 GiB

### Upgrading

Running [pipx upgrade](https://pipx.pypa.io/stable/docs/#pipx-upgrade)
upgrades lancet to the latest version.

```
pipx upgrade ajt-lancet
```

Running [pipx upgrade-all](https://pipx.pypa.io/stable/docs/#pipx-upgrade-al)
upgrades all packages installed with `pipx`.

```
pipx upgrade-all
```

### Development Setup

Since [Ajatt-Tools](https://github.com/Ajatt-Tools) is a distributed effort, we **highly welcome new contributors**!
Install the project in development mode to easily test and commit your changes using `hatch`.

- Clone the repo.
- Install [hatch](https://github.com/pypa/hatch).
- CD into the repo and run `hatch shell`.
- Inside the hatch shell run `pip install -e .`.
- To run the app, run: `hatch run lancet`.

Try these libre code editors with [python](https://wiki.archlinux.org/title/Python) support:

- [pycharm-community-edition](https://archlinux.org/packages/?name=pycharm-community-edition)
- [vscodium](https://aur.archlinux.org/packages/vscodium)

## Autostart

Add the `lancet` command to your autostart so Lancet launches at login.

Here's an example for [i3wm](https://i3wm.org/):

```
exec --no-startup-id lancet
```
