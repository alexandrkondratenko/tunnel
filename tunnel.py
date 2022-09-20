'''
Created on Sep 18, 2022

@author: a_kondratenko
'''
from _struct import unpack, pack
import abc
from argparse import ArgumentParser
from enum import IntEnum, auto
import socket
import ssl
from threading import Thread
import time


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

class MemoryOutputStream(BinaryOutputStream):
    def __init__(self):
        self.__data = bytes()
    def write(self, data):
        self.__data += data
    @property
    def data(self):
        return self.__data

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
    def close(self):
        self.__sock.close()

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
    def close(self):
        self.__sock.close()

PROTOCOL_VERSION = "2022.09.20-07.12.47"

class Message(IntEnum):
    Allocate = auto()
    Cid = auto()
    Connect = auto()
    Close = auto()
    Data = auto()
    KeepAlive = auto()

class KeepAlive(Thread):
    def __init__(self, connection, period):
        Thread.__init__(self)
        self.__connection = connection
        self.__period = period
        self.__stream = MemoryOutputStream()
        self.__stream.writePackedUInt64(Message.KeepAlive)
    def run(self):
        try:
            while True:
                time.sleep(self.__period)
                self.__connection.write(self.__stream.data)
        except:
            pass
        self.__connection.close()

if __name__ == '__main__':
    parser = ArgumentParser(description="TLS bidirectional tunnel")
    subparsers = parser.add_subparsers(dest="command")
    server = subparsers.add_parser("server")
    server.add_argument("port", help="port to listen for a tunnel client", type=int)
    server.add_argument("--target", help="host of the tunnel target, default is localhost", default="localhost")
    server.add_argument("--forward", help="ports to forward to a tunnel server", type=int, nargs='+', default=[])
    server.add_argument("--reconnect", help="time to reconnect, in seconds, default is 60", type=int, default=60)
    server.add_argument("--keepalive", help="period to send keepalive messages, in seconds, default is 60", type=int, default=60)
    client = subparsers.add_parser("client")
    client.add_argument("host", help="host of the server to connect to")
    client.add_argument("port", help="port of the server to connect to", type=int)
    client.add_argument("--target", help="host of the tunnel target, default is localhost", default="localhost")
    client.add_argument("--forward", help="ports to forward to a tunnel client", type=int, nargs='+', default=[])
    client.add_argument("--reconnect", help="time to reconnect, in seconds, default is 60", type=int, default=60)
    client.add_argument("--keepalive", help="period to send keepalive messages, in seconds, default is 60", type=int, default=60)
    args = parser.parse_args()
    while True:
        print("TLS bidirectional tunnel")
        print(f"local version = \"{PROTOCOL_VERSION}\"")
        if args.command == "server":
            print("server mode")
            connection = ServerConnection(args.port)
        else:
            print("client mode")
            connection = ClientConnection(args.host, args.port)
        print("connected")
        stream = MemoryOutputStream()
        stream.writeString(PROTOCOL_VERSION)
        stream.writePackedUInt64(len(args.forward))
        for forward in args.forward:
            stream.writePackedUInt64(forward)
        connection.write(stream.data)
        version = connection.readString()
        print(f"remote version = \"{version}\"")
        if version != PROTOCOL_VERSION:
            raise Exception(f"Wrong version \"{version}\"")
        size = connection.readPackedUInt64()
        ports = []
        for _ in range(size):
            port = connection.readPackedUInt64()
            ports.append(port)
        keepalive = KeepAlive(connection, args.keepalive)
        keepalive.start()
        while True:
            msg = connection.readPackedUInt64()
            if msg == Message.Allocate:
                print("allocate()")
            elif msg == Message.Cid:
                cid = connection.readPackedUInt64()
                print(f"cid({cid})")
            elif msg == Message.Connect:
                cid = connection.readPackedUInt64()
                port = connection.readPackedUInt64()
                print(f"connect({cid}, {port})")
            elif msg == Message.Close:
                cid = connection.readPackedUInt64()
                print(f"close({cid})")
            elif msg == Message.Data:
                cid = connection.readPackedUInt64()
                size = connection.readPackedUInt64()
                data = connection.read(size)
                print(f"data({cid}, {size})")
            elif msg == Message.KeepAlive:
                print("keepalive()")
            else:
                raise Exception(f"Unknown msg {msg}")
