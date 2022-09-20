'''
Created on Sep 18, 2022

@author: a_kondratenko
'''
from _struct import unpack, pack
import abc
from argparse import ArgumentParser, Action
from enum import IntEnum, auto
import math
import socket
import ssl
from threading import Thread, Lock
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
    __ALIGNMENT = 1024
    def __init__(self):
        self.__data = bytearray(MemoryOutputStream.__ALIGNMENT)
        self.__view = memoryview(self.__data)
        self.__pos = 0
    def write(self, data):
        size = len(data)
        if self.__pos + size > len(self.__data):
            newSize = math.floor((self.__pos + size - 1)/MemoryOutputStream.__ALIGNMENT + 1)*MemoryOutputStream.__ALIGNMENT
            view = self.__view
            self.__data = bytearray(newSize)
            self.__view = memoryview(self.__data)
            self.__view[:self.__pos] = view[:self.__pos]
        self.__view[self.__pos:self.__pos + size] = data
        self.__pos += size
    @property
    def data(self):
        return self.__view[:self.__pos]
    def reset(self):
        self.__pos = 0

class ServerConnection(BinaryInputStream, BinaryOutputStream):
    def __init__(self, port, cert, key):
        self.__port = port
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        sock.bind(("0.0.0.0", self.__port))
        sock.listen()
        conn, addr = sock.accept()
        self.__sock = context.wrap_socket(conn, server_side=True)
        self.__lock = Lock()
    def read(self, size):
        data = bytes()
        while len(data) < size:
            data += self.__sock.recv(size - len(data))
        return data
    def write(self, data):
        self.__lock.acquire()
        self.__sock.sendall(data)
        self.__lock.release()
    def close(self):
        self.__sock.close()

class ClientConnection(BinaryInputStream, BinaryOutputStream):
    def __init__(self, host, port, cert):
        self.__host = host
        self.__port = port
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cert)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.__sock = context.wrap_socket(sock)
        self.__sock.connect((self.__host, self.__port))
        self.__lock = Lock()
    def read(self, size):
        data = bytes()
        while len(data) < size:
            data += self.__sock.recv(size - len(data))
        return data
    def write(self, data):
        self.__lock.acquire()
        self.__sock.sendall(data)
        self.__lock.release()
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

class TunnelConnection(Thread):
    def __init__(self, connections, cid, sock):
        Thread.__init__(self)
        self.__connections = connections
        self.__cid = cid
        self.__sock = sock
        self.__closed = False
    def run(self):
        stream = MemoryOutputStream()
        while True:
            try:
                data = self.__sock.recv(1024*1024)
                if not data:
                    raise Exception("Socket closed")
                stream.writePackedUInt64(Message.Data)
                stream.writePackedUInt64(self.__cid)
                stream.writePackedUInt64(len(data))
                stream.write(data)
                self.__connections.write(stream.data)
                stream.reset()
            except:
                break
        if not self.__closed:
            print(f"disconnect({self.__cid})")
            stream.writePackedUInt64(Message.Close)
            stream.writePackedUInt64(self.__cid)
            self.__connections.write(stream.data)
            stream.reset()
            self.__connections.remove(self.__cid)
    def send(self, data):
        self.__sock.sendall(data)
    def close(self):
        self.__closed = True
        self.__sock.close()
        self.join()

class TunnelConnections(object):
    def __init__(self, connection, server):
        self.__connection = connection
        self.__server = server
        self.__connections = {}
        self.__allocated = set()
        self.__cids = []
        self.__lock = Lock()
        self.__stream = MemoryOutputStream()
    def allocate(self):
        self.__lock.acquire()
        if self.__server:
            cid = 0
            while cid in self.__allocated:
                cid += 1
            self.__allocated.add(cid)
        else:
            self.__stream.writePackedUInt64(Message.Allocate)
            self.__connection.write(self.__stream.data)
            self.__stream.reset()
            while not len(self.__cids):
                self.__lock.release()
                time.sleep(0.1)
                self.__lock.acquire()
            cid = self.__cids.pop(0)
        self.__lock.release()
        return cid
    def connect(self, cid, sock):
        connection = TunnelConnection(self, cid, sock)
        self.__connections[cid] = connection
        connection.start()
    def close(self, cid):
        self.__connections[cid].close()
    def remove(self, cid):
        del self.__connections[cid]
        if cid in self.__allocated:
            self.__allocated.remove(cid)
    def cid(self, cid):
        self.__lock.acquire()
        self.__cids.append(cid)
        self.__lock.release()
    def write(self, data):
        self.__connection.write(data)
    def send(self, cid, data):
        self.__connections[cid].send(data)
    def closeall(self):
        for connection in self.__connections.values():
            connection.close()
        self.__connections = {}

class TunnelPort(Thread):
    def __init__(self, connections, port, mapped):
        Thread.__init__(self)
        self.__connections = connections
        self.__port = port
        self.__mapped = mapped
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    def run(self):
        try:
            self.__sock.bind(("0.0.0.0", self.__mapped))
            self.__sock.listen()
            print(f"listen({self.__mapped}) --> {self.__port}")
            stream = MemoryOutputStream()
            while True:
                conn, addr = self.__sock.accept()
                cid = self.__connections.allocate()
                print(f"local connection {addr}")
                stream.writePackedUInt64(Message.Connect)
                stream.writePackedUInt64(cid)
                stream.writePackedUInt64(self.__port)
                self.__connections.write(stream.data)
                stream.reset()
                self.__connections.connect(cid, conn)
        except:
            pass
    def close(self):
        self.__sock.close()
        self.join()

class MappingAction(Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        Action.__init__(self, option_strings, dest, nargs, **kwargs)
    def __call__(self, parser, namespace, values, option_string=None):
        mapping = {}
        ports = {}
        for value in values:
            pair = value.split(":")
            if len(pair) != 2:
                parser.error("Mapping must use colon as separator")
            for item in pair:
                if not item.isdigit():
                    parser.error("Mapping must contain digits oly")
            port, mapped = list(map(int, pair))
            if port in mapping:
                parser.error("Mapping port duplication")
            if mapped in ports:
                parser.error("Mapped port duplication")
            mapping[port] = mapped
            ports[mapped] = port
        setattr(namespace, self.dest, mapping)

if __name__ == '__main__':
    parser = ArgumentParser(description="TLS bidirectional tunnel")
    subparsers = parser.add_subparsers(dest="command")
    server = subparsers.add_parser("server")
    server.add_argument("port", help="port to listen for a tunnel client", type=int)
    server.add_argument("--target", help="host of the tunnel target, default is localhost", default="localhost")
    server.add_argument("--forward", help="ports to forward to a tunnel server", type=int, nargs='+', default=[])
    server.add_argument("--reconnect", help="time to reconnect, in seconds, default is 60", type=int, default=60)
    server.add_argument("--keepalive", help="period to send keepalive messages, in seconds, default is 60", type=int, default=60)
    server.add_argument("--mapping", action=MappingAction, help="ports mapping to connect to", nargs='+', default={})
    server.add_argument("--cert", help="path to the certificate in PEM format, default is tunnel.crt", default="tunnel.crt")
    server.add_argument("--key", help="path to the private key in PEM format, default is tunnel.key", default="tunnel.key")
    client = subparsers.add_parser("client")
    client.add_argument("host", help="host of the server to connect to")
    client.add_argument("port", help="port of the server to connect to", type=int)
    client.add_argument("--target", help="host of the tunnel target, default is localhost", default="localhost")
    client.add_argument("--forward", help="ports to forward to a tunnel client", type=int, nargs='+', default=[])
    client.add_argument("--reconnect", help="time to reconnect, in seconds, default is 60", type=int, default=60)
    client.add_argument("--keepalive", help="period to send keepalive messages, in seconds, default is 60", type=int, default=60)
    client.add_argument("--mapping", action=MappingAction, help="ports mapping to connect to", nargs='+', default={})
    client.add_argument("--cert", help="path to the certificate in PEM format, default is tunnel.crt", default="tunnel.crt")
    args = parser.parse_args()
    connections = None
    ports = None
    keepalive = None
    while True:
        try:
            print("TLS bidirectional tunnel")
            print(f"local version = \"{PROTOCOL_VERSION}\"")
            if args.command == "server":
                print("server mode")
                connection = ServerConnection(args.port, args.cert, args.key)
            else:
                print("client mode")
                connection = ClientConnection(args.host, args.port, args.cert)
            print("connected")
            stream = MemoryOutputStream()
            stream.writeString(PROTOCOL_VERSION)
            stream.writePackedUInt64(len(args.forward))
            for forward in args.forward:
                stream.writePackedUInt64(forward)
            connection.write(stream.data)
            stream.reset()
            version = connection.readString()
            print(f"remote version = \"{version}\"")
            if version != PROTOCOL_VERSION:
                raise Exception(f"Wrong version \"{version}\"")
            connections = TunnelConnections(connection, args.command == "server")
            size = connection.readPackedUInt64()
            ports = []
            for _ in range(size):
                port = connection.readPackedUInt64()
                mapped = args.mapping[port] if port in args.mapping else port
                tunnel = TunnelPort(connections, port, mapped)
                ports.append(tunnel)
                tunnel.start()
            keepalive = KeepAlive(connection, args.keepalive)
            keepalive.start()
            while True:
                msg = connection.readPackedUInt64()
                if msg == Message.Allocate:
                    cid = connections.allocate()
                    print(f"allocate --> {cid}")
                    stream.writePackedUInt64(Message.Cid)
                    stream.writePackedUInt64(cid)
                    connection.write(stream.data)
                    stream.reset()
                elif msg == Message.Cid:
                    cid = connection.readPackedUInt64()
                    print(f"cid({cid})")
                    connections.cid(cid)
                elif msg == Message.Connect:
                    cid = connection.readPackedUInt64()
                    port = connection.readPackedUInt64()
                    print(f"connect({cid}, {port})")
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    if port not in args.forward:
                        raise Exception(f"Port {port} is not allowed to connect")
                    sock.connect((args.target, port))
                    connections.connect(cid, sock)
                elif msg == Message.Close:
                    cid = connection.readPackedUInt64()
                    print(f"close({cid})")
                    connections.close(cid)
                    connections.remove(cid)
                elif msg == Message.Data:
                    cid = connection.readPackedUInt64()
                    size = connection.readPackedUInt64()
                    data = connection.read(size)
                    print(f"data({cid}, {size})")
                    connections.send(cid, data)
                elif msg == Message.KeepAlive:
                    print("keepalive()")
                else:
                    raise Exception(f"Unknown msg {msg}")
        except:
            if ports:
                for port in ports:
                    port.close()
                ports = None
            if connections:
                connections.closeall()
                connections = None
            if keepalive:
                keepalive.join()
                keepalive = None
            time.sleep(args.reconnect)
