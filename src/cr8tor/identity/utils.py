import os
import string
import secrets


def generate_temp_password(length=16):
    """ Generate a random temporary password for a user.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def write_passwords(username, temp_password, directory="/tmp/user-passwords"):
    """ Write the temporary password for a user to a file.
    """
    os.makedirs(directory, exist_ok=True)
    file_path = os.path.join(directory, f"{username}.txt")

    with open(file_path, "w") as f:
        f.write(f"Temporary password for {username}: {temp_password}\n")

    print(f"[PasswordGenerator] Temp password for {username} written to {file_path}")