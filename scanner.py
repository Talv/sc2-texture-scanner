import os
import xml.etree.ElementTree as ET
import png
import re
from construct import (
    Struct, Const, Int32ul, Padding
)
from multiprocessing import Pool, cpu_count


T3_TEXTURE_HEADER = Struct(
    Const(b"MASK"),
    "version" / Int32ul,
    "unknown" / Int32ul,
    "sizeX" / Int32ul,
    "sizeY" / Int32ul,
    Padding(11 * 4)
)


class T3TextureReader(object):
    def __init__(self):
        self.snowIndex = -1
        self.snowValue = -1
        self.filename = None
        self.header = None
        self.blocksX = None
        self.blocksY = None
        self.map = None
        self.progressCb = None

    def open(self, filename):
        self.filename = filename
        with open(filename, "rb") as f:
            self.header = T3_TEXTURE_HEADER.parse_stream(f)
            self.blocksX = int(self.header.sizeX / 8 / 8)
            self.blocksY = int(self.header.sizeX / 8 / 8)
            self.blocksNum = int(self.blocksX * self.blocksY)
            self.layerSize = int(self.blocksNum * 8 * 8 * 64 / 2)

    def alloc(self):
        self.map = [
            None for layer in range(8)
        ]

    def readLayer(self, data):
        offset = 0
        layerPixels = [
            [
                None for x in range(self.header.sizeX)
            ] for y in range(self.header.sizeY)
        ]
        for block in range(self.blocksNum):
            for line in range(8):
                for y in range(8):
                    for x in range(64):
                        if x % 2 == 0:
                            # byte = f.read(1)[0]
                            byte = data[offset]
                            offset += 1
                            result = byte >> 4
                        else:
                            result = byte & 0x0F
                        absY = int(block / self.blocksX) * 64 + (line * 8) + y
                        absX = int(block % self.blocksX) * 64 + x
                        # pixels[offset - 1] = result
                        # self.map[layerId][absY][absX] = result
                        layerPixels[absY][absX] = result
            if self.progressCb:
                r = self.progressCb(
                    layerId * int(self.blocksX * self.blocksY) + block + 1,
                    8 * int(self.blocksX * self.blocksY)
                )
                if not r:
                    return
        return layerPixels

    def readMap(self):
        self.alloc()

        with open(self.filename, "rb") as f:
            f.seek(64, os.SEEK_SET)
            data = []

            for layerId in range(8):
                data.append(f.read(self.layerSize))
            with Pool(processes=cpu_count()) as p:
                for layerId, layerPixels in enumerate(p.map(self.readLayer, data)):
                    self.map[layerId] = layerPixels

    def getBoldestLayerAt(self, x, y):
        bestValue = None
        bestId = None
        for layerId in range(8):
            value = self.map[layerId][y][x]
            if layerId == self.snowIndex and value <= self.snowValue:
                continue
            if not bestValue or value > bestValue:
                bestValue = value
                bestId = layerId
        return bestId


def readTextureList(filename):
    with open(filename, "r") as f:
        root = ET.fromstring(f.read())
        for texture in root.iter("texture"):
            if int(texture.get('i')) >= 8:
                break
            yield texture.get('name')


re_snow_index = r'snow_index=([0-9]+)'
re_snow_value = r'snow_value=([0-9]+)'
def readSnowData(filename):
    snow_index = 0
    snow_value = 0
    with open(filename, "r") as f:
        f.readline()
        res = re.search(re_snow_index, f.readline())
        snow_index = res.group(1)
        res = re.search(re_snow_value, f.readline())
        snow_value = res.group(1)
    return [int(snow_index), int(snow_value)]


class ScriptWriter(object):
    def __init__(self, t3Reader, progressCb=None):
        self.outf = None
        self.t3Reader = t3Reader
        self.progressCb = progressCb
        self.xwidth = min([t3Reader.header.sizeX, 1024])

    def encodeChunk(self, buff, y, xoffset, count):
        buff.append("\"")
        for x in range(count):
            buff.append(str(self.t3Reader.getBoldestLayerAt(xoffset + x, y)))
        buff.append("\"")

    def encodeLine(self, buff, y):
        buff.append("tm[%d]=" % y)
        self.encodeChunk(buff, y, 0, self.xwidth)
        if self.t3Reader.header.sizeX > self.xwidth:
            buff.append('\n+')
            self.encodeChunk(buff, y, self.xwidth, self.t3Reader.header.sizeX - self.xwidth)
        buff.append(";\n")

    def encodeLineSection(self, c):
        buff = []
        lineCount = int(self.t3Reader.header.sizeY / cpu_count())
        for y in range(int(c * lineCount), int((c + 1) * lineCount)):
            # buff.append(self.encodeLine(y))
            self.encodeLine(buff, y)
        return ''.join(buff)


    def writeScript(self, filename, snow_index, snow_value):
        outf = open(filename, "w")
        outf.write(
"""
// snow_index=%d
// snow_value=%d
string[%d] tm;
void initTextureMap() {
"""
            % (snow_index, snow_value, self.t3Reader.header.sizeY)
        )
        # for y in range(self.t3Reader.header.sizeY):
        #     outf.write(self.encodeLine(y))

        with Pool(processes=cpu_count()) as p:
            for section in p.map(self.encodeLineSection, range(cpu_count())):
                outf.write(section)

        outf.write("}\n")
        outf.close()


def writeImage(filename, t3Reader):
    s = []
    for y in reversed(range(0, t3Reader.header.sizeY)):
        row = []
        for x in range(0, t3Reader.header.sizeX):
            row.append(t3Reader.getBoldestLayerAt(x, y) * 8)
        s.append(row)

    f = open(filename, 'wb')
    w = png.Writer(len(s[0]), len(s), greyscale=True, bitdepth=8)
    w.write(f, s)
    f.close()
