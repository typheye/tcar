#!/usr/bin/env python3
"""Small tagged logger designed for both journald and interactive runs."""

import os
import sys
import threading
import traceback
from datetime import datetime

DEBUG = 0
INFO = 1
WARNING = 2
ERROR = 3
CRITICAL = 4

_LEVEL_NAMES = {DEBUG: "D", INFO: "I", WARNING: "W", ERROR: "E", CRITICAL: "C"}
_level = DEBUG
_timestamps = False
_tag_width = 14
_loggers = {}
_lock = threading.RLock()
_file = None
_stdout = sys.stdout
_stderr = sys.stderr
_capture_installed = False


def set_level(level):
    global _level
    if level not in _LEVEL_NAMES:
        raise ValueError(f"invalid log level: {level}")
    _level = level


def enable_timestamps(enabled=True):
    global _timestamps
    _timestamps = bool(enabled)


def setup_file_log(path, append=True):
    global _file
    close_file_log()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    _file = open(path, "a" if append else "w", encoding="utf-8")


def close_file_log():
    global _file
    if _file is not None:
        try:
            _file.flush()
            _file.close()
        finally:
            _file = None


class Logger:
    def __init__(self, tag):
        self.tag = str(tag)

    def debug(self, message, *args): self._emit(DEBUG, message, *args)
    def info(self, message, *args): self._emit(INFO, message, *args)
    def warning(self, message, *args): self._emit(WARNING, message, *args)
    def error(self, message, *args): self._emit(ERROR, message, *args)
    def critical(self, message, *args): self._emit(CRITICAL, message, *args)

    def exception(self, message, *args):
        self._emit(ERROR, message, *args)
        trace = traceback.format_exc().strip()
        if trace and trace != "NoneType: None":
            for line in trace.splitlines():
                self._emit(ERROR, line)

    def _emit(self, level, message, *args):
        if level < _level:
            return
        if args:
            try:
                message = message % args
            except TypeError:
                message = " ".join([str(message), *(str(value) for value in args)])
        prefix = f"{_LEVEL_NAMES[level]} | {self.tag.ljust(_tag_width)} | "
        if _timestamps:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            prefix = f"[{timestamp}] {prefix}"
        stream = _stderr if level >= ERROR else _stdout
        with _lock:
            for part in str(message).splitlines() or [""]:
                line = prefix + part
                print(line, file=stream, flush=True)
                if _file is not None:
                    _file.write(line + "\n")
                    _file.flush()


def get_logger(tag):
    with _lock:
        logger = _loggers.get(tag)
        if logger is None:
            logger = Logger(tag)
            _loggers[tag] = logger
        return logger


class _CapturedStream:
    def __init__(self, stream, tag, level):
        self.stream = stream
        self.logger = get_logger(tag)
        self.level = level
        self.local = threading.local()

    @property
    def encoding(self): return getattr(self.stream, "encoding", "utf-8")
    @property
    def buffer(self): return self.stream.buffer
    def isatty(self): return self.stream.isatty()
    def fileno(self): return self.stream.fileno()

    def write(self, data):
        value = getattr(self.local, "pending", "") + str(data)
        lines = value.split("\n")
        self.local.pending = lines.pop()
        for line in lines:
            if line.rstrip("\r"):
                self.logger._emit(self.level, line.rstrip("\r"))
        return len(str(data))

    def flush(self):
        pending = getattr(self.local, "pending", "").rstrip("\r")
        if pending:
            self.logger._emit(self.level, pending)
            self.local.pending = ""
        self.stream.flush()


def install_print_capture():
    global _capture_installed
    if _capture_installed:
        return
    sys.stdout = _CapturedStream(_stdout, "STDOUT", INFO)
    sys.stderr = _CapturedStream(_stderr, "STDERR", ERROR)
    _capture_installed = True


def restore_print_capture():
    global _capture_installed
    if not _capture_installed:
        return
    sys.stdout, sys.stderr = _stdout, _stderr
    _capture_installed = False

