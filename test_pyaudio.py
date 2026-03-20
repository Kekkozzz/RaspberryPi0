import pyaudio
import os
from contextlib import contextmanager

@contextmanager
def suppress_stderr():
    null_fd = os.open(os.devnull, os.O_RDWR)
    save_fd = os.dup(2)
    os.dup2(null_fd, 2)
    try:
        yield
    finally:
        os.dup2(save_fd, 2)
        os.close(null_fd)
        os.close(save_fd)

print("Without suppress:")
p = pyaudio.PyAudio()
p.terminate()

print("With suppress:")
with suppress_stderr():
    p = pyaudio.PyAudio()
p.terminate()
