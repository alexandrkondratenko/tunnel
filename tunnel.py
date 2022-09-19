'''
Created on Sep 18, 2022

@author: a_kondratenko
'''
from _struct import unpack, pack
import abc


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

if __name__ == '__main__':
    pass