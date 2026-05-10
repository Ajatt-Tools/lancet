# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""
IPC command channel for Lancet.

Architecture:
- IpcServer owns an LancetIpcHTTPServer (subclass of http.server.HTTPServer)
  bound to bind_port, and a daemon thread that calls serve_forever.
- LancetIpcHTTPServer holds a signals reference.
  IpcRequestHandler accesses it via self.server.signals.
- A CLI invocation (lancet ocr, lancet screenshot, etc.) sends an HTTP POST to that server.
"""
