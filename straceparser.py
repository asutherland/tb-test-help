import pyparsing as pyp
import datetime

supLParen = pyp.Literal('(').suppress()
supRParen = pyp.Literal(')').suppress()
supEquals = pyp.Literal('=').suppress()
supColon  = pyp.Literal(':').suppress()
supLBrace = pyp.Literal('{').suppress()
supRBrace = pyp.Literal('}').suppress()
supLBracket = pyp.Literal('[').suppress()
supRBracket = pyp.Literal(']').suppress()
supDQuote = pyp.Literal('"').suppress()
supEllipsis = pyp.Literal('...').suppress()

funcName = pyp.Word(pyp.alphanums + '_').setResultsName('func')
pValue = pyp.Forward()
pNum = pyp.Combine(pyp.Optional('-') + pyp.Word(pyp.nums))
def actNum(s, l, toks):
    if toks[0].startswith('0'):
        if len(toks[0]) == 1:
            return 0
        else:
            return int(toks[0][1:], 8)
    else:
        return int(toks[0])
pNum.setParseAction(actNum)
pPtr = pyp.Combine(pyp.Literal('0x') + pyp.Word(pyp.nums + 'abcdefABCDEF'))
pStr = (pyp.dblQuotedString.setParseAction(pyp.removeQuotes) +
        pyp.Optional(supEllipsis))
#pStr = (supDQuote + pyp.Optional(pyp.CharsNotIn('"')) + supDQuote +
#        pyp.Optional(supEllipsis))
pConstant = pyp.Word(pyp.alphanums + '_')
pAggNum = pNum | pConstant
pAggNums = pyp.delimitedList(pAggNum, '|')
pKeyValPair = pyp.Group(pConstant + (supEquals|supColon) + pValue)

pValues = pyp.Forward()
pKeyValPairs = pyp.delimitedList(pKeyValPair | supEllipsis)
pNamedStruct = pyp.Group(pyp.Dict(supLBrace + pKeyValPairs + supRBrace))
pAnonStruct = supLBrace + pValues + supRBrace
pStruct = (pNamedStruct | pAnonStruct)
pList = supLBracket + pValues + supRBracket
# this now handles both cast(value) and cast(value, value, ...)
pCasty = pyp.Group(pConstant + supLParen + pValues + supRParen)

# It's absurd because it's bare.
# 2010/04/22-10:57:45
posNum2 = pyp.Word(pyp.nums, exact=2)
posNum4 = pyp.Word(pyp.nums, exact=4)
pAbsurdDateFmt = pyp.Combine(posNum4 + '/' + posNum2 + '/' + posNum2 +
                             '-' + posNum2 + ':' + posNum2 + ':' + posNum2)
def actAbsurdDateFmt(s, l, toks):
    return datetime.datetime.strptime(toks[0], "%Y/%m/%d-%H:%M:%S")
pAbsurdDateFmt.setParseAction(actAbsurdDateFmt)

pValue << (pAbsurdDateFmt | pPtr | pCasty | pAggNums | pStr | pStruct | pList)
pValues << pyp.Group(pyp.Optional(pyp.delimitedList(pValue)))

pParenData = pyp.Optional(pyp.Literal('in')|pyp.Literal('out')) + pList
pExplanation = pyp.Word(pyp.alphas + ' ')
pOutInfo = supLParen + (pParenData | pExplanation) + supRParen
namedArgs = pyp.Group(pyp.Dict(pyp.delimitedList(pKeyValPair | pNamedStruct)))
funcArgs = namedArgs | pValues
funcLine = (funcName + supLParen +
            funcArgs.setResultsName('args')+
            supRParen + supEquals +
            pNum.setResultsName('rval') +
            pyp.Optional(pConstant).setResultsName('err') +
            pyp.Optional(pOutInfo).setResultsName('errexpl'))

#pPtr.setParseAction(lambda s, l, toks: int(toks[0], 16))

import pprint

def dumpalyze(results):
    pprint.pprint(results.asList())
    pprint.pprint(dict(results.items()))
    return results

def test():
    values = '''1234
0
1234, 5
0x13
{1234, 0x1234}
FUTEX_WAKE_OP_PRIVATE
{FUTEXT_WAKE_OP_PRIVATE, 10}
4, {FUTEXT_WAKE_OP_PRIVATE, 10}
{fd=1, bob=4}
{fd=1, events=POLLIN}
{fd=1, events=POLLIN|POLLPRI}
[0]
[0, {fd=1}]
""...
{""..., 0}
0644
O_RDONLY|0644
{st_mode=S_IFREG|0644, st_size=1997}
{st_mode=S_IFREG|0644, st_size=1997, ...}
[3, {st_mode=S_IFREG|0644, st_size=1997, ...}]
{entry_number:6, base_addr:0xb42ffb90, limit:1048575}
{entry_number:6, base_addr:0xb42ffb90, limit:1048575, seg_32bit:1, foo:0}
{st_mtime=2010/04/22-10:57:45, st_ctime=2010/04/22-10:57:45}
'''

    for line in values.splitlines():
        print '.' * 80
        print line
        results = pValues.parseString(line)
        dumpalyze(results)

    lines = '''gettimeofday({1236856179, 761956}, NULL) = 0
fake(0) = 1
fake(0xb6a7bf88, FUTEX_WAKE_OP_PRIVATE) = 1
futex(0xb6a7bf88, FUTEX_WAKE_OP_PRIVATE, 1, 1, 0xb6a7bf84, {FUTEX_OP_SET, 0, FUTEX_OP_CMP_GT, 1}) = 1
gettimeofday({1236856179, 762054}, NULL) = 0
gettimeofday({1236856179, 762108}, NULL) = 0
fake(0) = 1 ([{fd=19, revents=POLLIN}])
poll([{fd=4, events=POLLIN}, {fd=3, events=POLLIN}, {fd=8, events=POLLIN|POLLPRI}, {fd=12, events=POLLIN|POLLPRI}, {fd=13, events=POLLIN|POLLPRI}, {fd=14, events=POLLIN|POLLPRI}, {fd=18, events=POLLIN}, {fd=10, events=POLLIN|POLLPRI}, {fd=19, events=POLLIN}], 9, 0) = 1 ([{fd=19, revents=POLLIN}])
select(4, [3], [3], NULL, NULL)         = 1 (out [3])
writev(3, [{"$\7\1\0&\0\2\0|\0\0\0"..., 12}, {NULL, 0}, {""..., 0}], 3) = 12
select(4, [3], [], NULL, NULL) = 1 (in [3])
read(3, "\1\0013\316\0\0\0\0|\0\0\0\220\22 \1E\1u\0E\1u\0\0\0\0\0\370\236\246\10"..., 4096) = 32
stat64("/foo/bar/baz", {st_mode=S_IFREG|0644, st_size=1997, ...}) = 0
clone(foo=0, bar=0) = 0
clone(child_stack=0xb42ff464, flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM|CLONE_SETTLS|CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID, parent_tidptr=0xb42ffbd8, {entry_number:6, base_addr:0xb42ffb90, limit:1048575, seg_32bit:1, contents:0, read_exec_only:0, limit_in_pages:1, seg_not_present:0, useable:1}, child_tidptr=0xb42ffbd8) = 6928
connect(60, {sa_family=AF_INET, sin_port=htons(993), sin_addr=inet_addr("72.249.41.52")}, 16) = -1 EINPROGRESS (Operation now in progress)
fstat(42, {st_dev=makedev(253, 0)}) = 0
fstat(42, {st_dev=makedev(253, 0), st_ino=398426, st_mode=S_IFREG|0644, st_nlink=1, st_uid=500, st_gid=500, st_blksize=4096, st_blocks=15408, st_size=7882568, st_atime=2010/04/22-10:57:49, st_mtime=2010/04/22-10:57:45, st_ctime=2010/04/22-10:57:45}) = 0
'''

    for line in lines.splitlines():
        print '-' * 80
        print 'LINE', line
        results = funcLine.parseString(line)
        dumpalyze(results)

if __name__ == '__main__':
    test()
