import os

from cryptography.fernet import Fernet


def _get_cipher():
    encryption_key = os.getenv(
        "TOKEN_ENCRYPTION_KEY"
    )

    if not encryption_key:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY environment variable "
            "is not set"
        )

    try:
        return Fernet(
            encryption_key.encode()
        )
    except Exception as exc:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is invalid"
        ) from exc


def encrypt_token(token):
    if not token:
        raise ValueError(
            "Token cannot be empty"
        )

    cipher = _get_cipher()

    return cipher.encrypt(
        token.encode()
    ).decode()


def decrypt_token(encrypted_token):
    if not encrypted_token:
        raise ValueError(
            "Encrypted token cannot be empty"
        )

    cipher = _get_cipher()

    return cipher.decrypt(
        encrypted_token.encode()
    ).decode()