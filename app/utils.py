import petname
import random
import logging
import base64
import sys
from typing import Optional
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization

def generate_public_key(private_key_str: str) -> str:
    """
    Generate a WireGuard public key from a given private key.

    Args:
        private_key_str (str): The base64-encoded private key.

    Returns:
        str: The base64-encoded public key.
    """
    # Decode the private key from base64
    private_key_bytes = base64.b64decode(private_key_str)

    # Create an X25519 private key object
    private_key = X25519PrivateKey.from_private_bytes(private_key_bytes)

    # Generate the corresponding public key
    public_key = private_key.public_key()

    # Encode the public key to base64 using the correct encoding and format
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    public_key_base64 = base64.b64encode(public_key_bytes).decode("utf-8")

    return public_key_base64# Example usage

def generate_projectname():
    # Generates a unique two-word name
    return petname.Generate(2, separator="-")

def generate_peername(projectname):
    """
    Generates a unique, human-readable peer name based on project name.
    Format: [proj_prefix]-[word][number]
    Example: if project is 'happy-dolphin', peer could be 'hd-coral7'

    The format ensures:
    1. Project relation (using prefix)
    2. Readability (using real word)
    3. Uniqueness (using number)
    4. Max 15 chars length
    """
    # Get project prefix (e.g., 'happy-dolphin' -> 'hd')
    words = projectname.split('-')
    prefix = ''.join(word[0] for word in words)
    # Generate a short animal/adjective name (4-6 chars)
    while True:
        word = petname.Generate(1)
        if 4 <= len(word) <= 6:
            break
    # Calculate remaining space for the numeric suffix
    # Format will be: prefix-word#
    # Since word is guaranteed to be 4-6 chars and prefix is typically 2 chars,
    # we'll always have at least some space for a number
    remaining_space = 15 - (len(prefix) + 1 + len(word))
    # Generate a random number that fits in remaining space
    num = random.randint(1, min(9999, 10 ** remaining_space - 1))
    return f"{prefix}-{word}{num}"

def setup_logger(
    name: str = "auto_vpn",
    log_level: int = logging.DEBUG,
    log_format: Optional[str] = None
) -> logging.Logger:
    """
    Configure logging to stderr with the specified format and level.
    
    Args:
        name: Logger name (default: "vpn_app")
        log_level: Logging level (default: logging.DEBUG)
        log_format: Custom log format string (optional)
        
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create console handler that writes to stderr
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    
    # Create formatter
    if log_format is None:
        log_format = '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    
    # Add formatter to handler
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    return logger
