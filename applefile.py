import struct
import cStringIO as StringIO

class Entry(object):
    def __init__(self, reader, id, offset, length):
        self._reader = reader
        self.id = id
        self.offset = offset
        self.length = length
    
    @property
    def data(self):
        return self._reader._getEntryBuf(self)

RESOURCE_FORK_ID = 2

ENTRY_ID_MAP = {
    1: 'Data Fork',
    2: 'Resource Fork',
    3: 'Real Name',
    4: 'Comment',
    5: 'Icon, B&W',
    6: 'Icon, Color',
    8: 'File Date Info',
    9: 'Finder Info',
    10: 'Attributes',
    11: 'ProDOS Info',
    12: 'MS-DOS Info',
    13: 'AFP Short Name',
    14: 'AFP File Info',
    15: 'AFP Directory ID'
}

class AppleFileReader(object):
    APPLE_SINGLE = 0x00051600
    APPLE_DOUBLE = 0x00051607
    
    def __init__(self, f):
        self.f = f
        self._readHeader()
    
    def _getEntryBuf(self, entry):
        self.f.seek(entry.offset)
        return self.f.read(entry.length)
    
    def _readEntry(self):
        return Entry(self, *struct.unpack('>iii', self.f.read(12)))
    
    def _readHeader(self):
        self.magic, self.version = struct.unpack('>ii', self.f.read(8))
        # on v1 this is the home file system
        # on v2 this is 'filler' and should be all zeroes
        self.homeFileSystem = self.f.read(16)
        num_entries, = struct.unpack('>h', self.f.read(2))
        
        self.isDouble = self.magic == self.APPLE_DOUBLE
        self.fileType = self.isDouble and "double" or "single"
        
        self.entries = []
        for i in range(num_entries):
            self.entries.append(self._readEntry())

class ResourceReference(object):
    def __init__(self, resourceID, name, attributes, dataOffset):
        self.id = resourceID
        self.name = name
        self.attributes = attributes
        self.offset = dataOffset

class ResourceType(object):
    def __init__(self, resourceType, count, refListOffset):
        self.type = resourceType
        self.count = count
        self.refListOffset = refListOffset
        
        self.references = []

class ResourceForkReader(object):
    def __init__(self, f):
        self.f = f
        
        self.resourceTypes = []
        
        self._readHeader()
        self._readResourceMap()

    
    def _readResourceTypeItem(self):
        resourceType = self.f.read(4)
        (numLessOne, refListOffRelTypeList) = struct.unpack('>hh', self.f.read(4))
        count = numLessOne + 1
        
        return ResourceType(resourceType, count,
                            refListOffRelTypeList + self.typeListOffset)
    
    def _readString(self, offset):
        self.f.seek(offset)
        length = ord(self.f.read(1))
        return self.f.read(length)
    
    def getRefDataLength(self, ref):
        self.f.seek(ref.offset)
        return struct.unpack('>I', self.f.read(4))[0]
    
    def _readResourceReferences(self, resourceType):
        REF_ITEM_SIZE = 12
        
        baseOffset = resourceType.refListOffset
        for offset in range(baseOffset,
                            baseOffset + REF_ITEM_SIZE * resourceType.count,
                            REF_ITEM_SIZE):
            self.f.seek(offset)
            (resourceID, nameRelOffset, attribs_and_resourceDataRelOff
                ) = struct.unpack('>HhI', self.f.read(8))
            # ignore handle reserved space (4)
            attribs = (attribs_and_resourceDataRelOff >> 24) & 0xff
            resourceDataRelOff = (attribs_and_resourceDataRelOff & 0xffffff)
            
            if resourceDataRelOff == 0xffff:
                name = None
            else:
                nameOffset = nameRelOffset + self.nameListOffset
                name = self._readString(nameOffset)
            
            dataOffset = self.dataOffset + resourceDataRelOff
            resourceType.references.append(
                ResourceReference(resourceID, name, attribs, dataOffset))
        
    
    def _readResourceMap(self):
        self.f.seek(self.mapOffset)
        # skip reserved header (16), next map handle (4), file ref num (2)
        self.f.seek(22, 1)
        (self.attribs, self.typeListRelOff, self.nameListRelOff,
            ) = struct.unpack('>Hhh', self.f.read(6))

        self.typeListOffset = self.mapOffset + self.typeListRelOff
        self.nameListOffset = self.mapOffset + self.nameListRelOff 
        
        # read resource types
        self.f.seek(self.typeListOffset)
        numTypesLessOne, = struct.unpack('>H', self.f.read(2))
        numTypes = numTypesLessOne + 1
        for i in range (numTypes):
            self.resourceTypes.append(self._readResourceTypeItem())
        
        # read type references
        map(self._readResourceReferences, self.resourceTypes)
        
    
    def _readHeader(self):
        (self.dataOffset, self.mapOffset, self.dataLength,
            self.resourceLength) = struct.unpack('>iiii', self.f.read(16))
        

class AppleFileDisplay(object):
    def __init__(self):
        pass
    
    def grok(self, f):
        if isinstance(f, basestring):
            f = StringIO.StringIO(f)
        self.fr = AppleFileReader(f)
    
    def grokFile(self, filename):
        f = open(filename, 'rb')
        self.grok(f)
    
    def showEntry(self, entry):
        print '%8.8x %8.8x %s' % (entry.offset, entry.length,
                                  ENTRY_ID_MAP.get(entry.id, 'Unknown Type'))
    
    def show(self):
        print 'Type:', self.fr.fileType
        for entry in self.fr.entries:
            self.showEntry(entry)
    
    def showResourceFork(self, rfr):
        for resourceType in rfr.resourceTypes:
            print '%s %d' % (resourceType.type, resourceType.count)
            for ref in resourceType.references:
                dataLength = rfr.getRefDataLength(ref)
                print '  %4.4x %s (%d)' % (ref.id, ref.name, dataLength) 
    
    def showResourceForks(self):
        for entry in self.fr.entries:
            if entry.id == RESOURCE_FORK_ID:
                rfdata = entry.data
                rfr = ResourceForkReader(StringIO.StringIO(rfdata))
                self.showResourceFork(rfr)

#if __name__ == '__main__':
#    import sys
#    afd = AppleFileDisplay()
#    afd.grokFile(sys.argv[0])
#    afd.show()
