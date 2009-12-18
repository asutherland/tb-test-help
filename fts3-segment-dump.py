class SegmentGobbler(object):
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def eat_varint(self):
        val = 0
        while True:
            byte = self.data[self.offset]
            self.offset += 1
            val = (val << 7) | (byte & 0x7f)
            if not (byte & 0x80):
                break
        return val

    def eat_byte(self):
        b = self.data[self.offset]
        self.offset += 1
        return b

    def eat_byte_string(self, length):
        bs = self.data[self.offset:self.offset+length]
        self.offset += length
        return "".join([chr(c) for c in bs])

    def eat_term(self):
        length = self.eat_varint()
        term_str = self.eat_byte_string(length)
        return term_str

    def eat_doclist_entry(self, last_docid=0):
        docid = self.eat_varint() + last_docid
        
        col_num = 0
        offsets = []
        results = []
        while True:
            # bytes are defined for the sentinel values, but they comply with
            #  the varint spec, so just eat a varint
            val = self.eat_varint()
            # update results if we accumulated any offsets for this column and
            #  we're hitting a sentinel value which means the end of this column
            if val < 2 and offsets:
                results.append([col_num, offsets])
            # 0 means the end!
            if val == 0:
                return docid, results
            # it's a new column!
            if val == 1:
                col_num = self.eat_varint()
                offsets = []
            else:
                offsets.append(val)

    def eat_doclist(self):
        endoffset = self.offset + self.eat_varint()
        docid = 0
        while self.offset < endoffset:
            docid, offsets_by_column = self.eat_doclist_entry(docid)
            print '  Doc:', docid
            print '   Results:', offsets_by_column

    def eat_leaf(self):
        term = None
        while self.offset < len(self.data):
            if term is None:
                term = self.eat_term()
            else:
                prefix_len = self.eat_varint()
                suffix = self.eat_term()
                prefix = term[:prefix_len]
                term = prefix + suffix
            print 'Term:', term, repr(term)
            docs = self.eat_doclist()

    def eat_btree(self):
        height = self.eat_varint()
        if height == 0:
            self.eat_leaf()
        else:
            print "I don't speak internal nodes yet."


def hexgobble(d):
    data = []
    for i in range(0, len(d), 2):
        data.append(int(d[i:i+2], 16))
    gobbler = SegmentGobbler(data)
    gobbler.eat_btree()

