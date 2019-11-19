import base64
import hashlib

from Crypto import Random
from Crypto.Cipher import AES


class CryptUtil():

    def __init__(self, password):
        self.key = hashlib.sha256(password.encode('utf-8')).digest()
        self.BS = 16

    pad = lambda self, s: s + (self.BS - len(s) % self.BS) * chr(self.BS - len(s) % self.BS)
    unpad = lambda self, s: s[0:-s[-1]]

    def encrypt(self, raw):
        raw = self.pad(raw)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw.encode('utf-8')))

    def decrypt(self, enc):
        if enc is None:
            return None
        enc = base64.b64decode(enc)
        iv = enc[:16]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self.unpad(cipher.decrypt(enc[16:])).decode('utf-8')