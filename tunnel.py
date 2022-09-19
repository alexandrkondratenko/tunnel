'''
Created on Sep 18, 2022

@author: a_kondratenko
'''
from _struct import unpack, pack
import abc
import socket
import ssl


class BinaryInputStream(object):
    __metaclass__ = abc.ABCMeta
    @abc.abstractmethod
    def read(self, size):
        raise NotImplementedError("BinaryInputStream is abstract")
    def readUInt8(self):
        return unpack("<B", self.read(1))[0]
    def readPackedUInt64(self):
        result = 0
        offset = 0
        for _ in range(0, 8):
            value8 = self.readUInt8()
            result |= (value8 & 0x7f) << offset
            if value8 & 0x80 == 0:
                return result
            offset += 7
        value8 = self.readUInt8()
        result |= value8 << offset
        return result
    def readString(self):
        size = self.readPackedUInt64()
        if size > 0:
            return self.read(size).decode("utf-8")
        return ""

class BinaryOutputStream(object):
    __metaclass__ = abc.ABCMeta
    @abc.abstractmethod
    def write(self, data):
        raise NotImplementedError("BinaryOutputStream is abstract")
    def writeUInt8(self, value):
        self.write(pack("<B", value))
    def writePackedUInt64(self, value):
        for _ in range(0, 8):
            if value < (1 << 7):
                self.writeUInt8(value & 0x7f)
                return
            self.writeUInt8((value & 0x7f) | 0x80)
            value >>= 7
        self.writeUInt8(value & 0xff)
    def writeString(self, value):
        data = value.encode("utf-8")
        size = len(data)
        self.writePackedUInt64(size)
        if size > 0:
            self.write(data)

class ServerConnection(BinaryInputStream, BinaryOutputStream):
    def __init__(self, port):
        self.__port = port
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain("tunnel.crt", "tunnel.key")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        sock.bind(("0.0.0.0", self.__port))
        sock.listen()
        conn, addr = sock.accept()
        self.__sock = context.wrap_socket(conn, server_side=True)
    def read(self, size):
        data = bytes()
        while len(data) < size:
            data += self.__sock.recv(size - len(data))
        return data
    def write(self, data):
        self.__sock.sendall(data)

class ClientConnection(BinaryInputStream, BinaryOutputStream):
    def __init__(self, host, port):
        self.__host = host
        self.__port = port
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.__sock = context.wrap_socket(sock)
        self.__sock.connect((self.__host, self.__port))
    def read(self, size):
        data = bytes()
        while len(data) < size:
            data += self.__sock.recv(size - len(data))
        return data
    def write(self, data):
        self.__sock.sendall(data)

if __name__ == '__main__':
    pass