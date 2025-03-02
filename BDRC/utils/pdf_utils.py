import os
import platform
import subprocess
import sys
from functools import wraps
from pdf2image import convert_from_path as original_convert_from_path
from pdf2image.pdf2image import pdfinfo_from_path as original_pdfinfo_from_path

# Flag to determine if we're on Windows
IS_WINDOWS = platform.system() == 'Windows'

# Windows-specific constant for CREATE_NO_WINDOW
CREATE_NO_WINDOW = 0x08000000

def run_hidden_process(*args, **kwargs):
    """
    Run a subprocess with hidden window on Windows.
    This is a wrapper around subprocess.run that adds the CREATE_NO_WINDOW flag on Windows.
    """
    if IS_WINDOWS:
        if 'creationflags' in kwargs:
            kwargs['creationflags'] |= CREATE_NO_WINDOW
        else:
            kwargs['creationflags'] = CREATE_NO_WINDOW
    return subprocess.run(*args, **kwargs)

def with_hidden_windows(func):
    """
    Decorator that temporarily replaces subprocess.Popen with a version
    that adds CREATE_NO_WINDOW flag on Windows.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not IS_WINDOWS:
            # On non-Windows platforms, just call the original function
            return func(*args, **kwargs)
            
        # Save the original subprocess.Popen
        original_popen = subprocess.Popen
        
        # Create a wrapper for subprocess.Popen that adds the CREATE_NO_WINDOW flag
        @wraps(original_popen)
        def popen_no_window(*popen_args, **popen_kwargs):
            # Add CREATE_NO_WINDOW flag to creationflags
            if 'creationflags' in popen_kwargs:
                popen_kwargs['creationflags'] |= CREATE_NO_WINDOW
            else:
                popen_kwargs['creationflags'] = CREATE_NO_WINDOW
            return original_popen(*popen_args, **popen_kwargs)
        
        # Replace subprocess.Popen with our wrapper
        subprocess.Popen = popen_no_window
        
        try:
            # Call the original function with our subprocess.Popen wrapper in effect
            return func(*args, **kwargs)
        finally:
            # Restore the original subprocess.Popen
            subprocess.Popen = original_popen
            
    return wrapper

@with_hidden_windows
def convert_from_path(*args, **kwargs):
    """
    Wrapper for pdf2image.convert_from_path that suppresses command windows on Windows
    """
    return original_convert_from_path(*args, **kwargs)

@with_hidden_windows
def pdfinfo_from_path(*args, **kwargs):
    """
    Wrapper for pdf2image.pdfinfo_from_path that suppresses command windows on Windows
    """
    return original_pdfinfo_from_path(*args, **kwargs)
