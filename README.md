<p align="center">
    <img width=200px height=200px src="lancet/icons/logo.png" alt="Project logo">
</p>

<p align="center">OCR application for reading manga in Japanese, made for AJATTers🇯🇵</p>

# Lancet

[![PyPi](https://img.shields.io/pypi/v/ajt-lancet?style=for-the-badge)](https://pypi.org/project/ajt-lancet/)
[![Chat](https://img.shields.io/badge/chat-join-green?style=for-the-badge&logo=Telegram&logoColor=green)](https://ajatt.top/blog/join-our-community.html)
[![Support](https://img.shields.io/badge/support-developer-orange?style=for-the-badge&logo=Patreon&logoColor=orange)](https://ajatt.top/blog/donating-to-tatsumoto.html)

Lancet is a OCR application for reading manga in Japanese.
It uses pytorch models to recognize Japanese text on images.
Lancet works best with [Goldendict-ng](https://xiaoyifang.github.io/goldendict-ng/)
or [Rikaitan](https://rikaitan.ajatt.top/).

https://user-images.githubusercontent.com/69171671/177458117-ba858b79-0b2e-4605-9985-5801d9685bd6.mp4

## User Guide

Prerequisites:

- [Goldendict](https://ajatt.top/blog/setting-up-goldendict.html) for looking up words in Japanese dictionaries.
- [nsxiv](https://wiki.archlinux.org/title/Sxiv) for reading manga.

Launch `Goldendict`, then open a manga folder in `nsxiv`.
Launch `Lancet` and wait for the OCR model to load.
Show the snipping window using shortcut `Alt+O` ("O" for OCR)
and drag and hold the mouse cursor to start performing OCR.

## Installation

Install using [pipx](https://pipx.pypa.io/stable/) from [pypi](https://pypi.org/project/ajt-lancet/).

```bash
pipx install ajt-lancet
```

The `lancet` executable will be available in $PATH.

### System Requirements

The program has to rely on large Python libraries to work.
`pipx` will install everything in one location, so you can cleanly uninstall it later with `pipx uninstall`.
Additionally, there are `pytorch` models from huggingface.
They will be downloaded and saved to `~/.cache/huggingface`.

- Hard drive: 8GiB (`pytorch` and its dependencies)
- RAM: at least 2 GB (recommended)

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
Install the project in development mode to easily test and commit your changes.
Contributors can install and set up Lancet using `hatch`.

- Clone the repo.
- Install [hatch](https://github.com/pypa/hatch).
- CD to the repo and run `hatch shell`.
- Inside the hatch shell, run `pip install -e .`.
- To run the app, run: `hatch run lancet`.

Try these libre code editors with [python](https://wiki.archlinux.org/title/Python) support:

- [pycharm-community-edition](https://archlinux.org/packages/?name=pycharm-community-edition)
- [vscodium](https://aur.archlinux.org/packages/vscodium)

## Autostart

Add the `lancet` command to autostart to start Lancet when you log in.

Here's an example for [i3wm](https://i3wm.org/):

```
exec --no-startup-id lancet
```
