import urlparse

class ImapLoop(object):
    def __init__(self, loop_id):
        self.loop_id = loop_id

class ImapUrl(object):
    __slots__ = ['urlstr', 'accountName', 'query', 'action', 'idType',
                 'folderPath', 'args', 'references', 'downloadedAtLine']

    def __init__(self, urlstr):
        self.urlstr = urlstr

        #print 'url', urlstr

        (trashScheme, self.accountName, path, trashParams, self.query,
         trashFragments) = urlparse.urlparse(urlstr)

        path_bits = path[1:].split('>')
        self.action = path_bits[0]

        if self.action == 'fetch':
            (self.idType, self.folderPath, self.args) = path_bits[1:]

        self.references = []

    def ref(self, iLine, thread, line):
        self.references.append((iLine, thread, line))

    @property
    def uids(self):
        if self.idType != 'UID':
            return ()
        
        uids = set()
        for part in self.args.split(','):
            if ':' in part:
                low, high = part.split(':')
                uids.update(range(int(low), int(high)+1))
            else:
                uids.add(int(part))

        return uids

        
class ImapFolder(object):
    def __init__(self, path):
        self.path = path
        self.downloadedUids = {}
        self.redundancies = []

    def noteDownloads(self, imap_url, iLine, thread_id):
        redundant = False
        for uid in imap_url.uids:
            if uid in self.downloadedUids:
                orig_url = self.downloadedUids[uid]
                self.redundancies.append((iLine, thread_id, uid,
                                          orig_url, orig_url.downloadedAtLine,
                                          imap_url))
                redundant = True

            imap_url.downloadedAtLine = iLine
            #print '%s downloading %d' % (self, uid)
            self.downloadedUids[uid] = imap_url
        return redundant

    def reportRedundancies(self):
        for (iLine, thread_id, uid, orig_url, orig_line,
             imap_url) in self.redundancies:
            print '!!! redundant download of %s in %s on thread %x' % (
                uid, self, thread_id)
            print '  previous:  %d: %s' % (orig_line,
                                           orig_url.urlstr)
            for iLine, thread_id, ref_str in orig_url.references:
                print '    %d: %x: %s' % (iLine, thread_id, ref_str)
            orig_url.references = []

            print '  redundant: %d: %s' % (iLine, imap_url.urlstr)
            for iLine, thread_id, ref_str in imap_url.references:
                print '    %d: %x: %s' % (iLine, thread_id, ref_str)
            print ''

    def __str__(self):
        return self.path
                         
class ImapLogParser(object):
    def __init__(self):
        self.threads = {}
        self.imapLoops = {}
        self.imapAccounts = {}

        self.all_urls = {}

        self.redundantFolders = []

    def get_or_create_url(self, urlstr):
        if urlstr in self.all_urls:
            return self.all_urls[urlstr]
        else:
            url = self.all_urls[urlstr] = ImapUrl(urlstr)
            return url

    def track_url_in_str(self, line):
        idx_url = line.find('url:')
        pre_url_str = line[:idx_url].strip()
        urlstr = line[idx_url+4:]
        imap_url = self.get_or_create_url(urlstr)

        imap_url.ref(self.iLine, self.thread_id, pre_url_str)

    def get_folder_for_imap_url(self, imap_url):
        account = self.imapAccounts.get(imap_url.accountName)
        if account is None:
            account = self.imapAccounts[imap_url.accountName] = {}
        folder = account.get(imap_url.folderPath)
        if folder is None:
            folder = account[imap_url.folderPath] = ImapFolder(
                                                        imap_url.folderPath)
        return folder

    def parse(self, f):
            self.iLine = 0
            for line in f:
                self.iLine += 1

                line = line.strip()
                # eat the "-timestamp[hex thread]: " lead-in
                idx = line.find('[')
                timestamp = int(line[1:idx])
                nidx = line.find(']', idx)
                self.thread_id = int(line[idx+1:nidx], 16)
                line = line[nidx + 3:]

                # now figure out the first 'word'
                idx_space = line.find(' ')
                idx_colon = line.find(':')

                # word is space-delimited?
                if (idx_colon == -1 or
                        (idx_space != -1 and idx_space < idx_colon)):
                    word = line[:idx_space]
                    meth_name = '_parse_%s' % (word,)
                    meth = getattr(self, meth_name, None)
                    if meth:
                        meth(line)
                    else:
                        print '*** No such method for word: %s' % (word,)

                    # ImapThreadMainLoop entering
                    # ImapThreadMainLoop leaving
                    # ReadNextLine
                    # queuing url:
                    # considering playing queued url:
                    # creating protocol instance to play queued url:
                    # failed creating protocol instance to play queued url:
                    # playing queued url:
                # otherwise it must be colon-delimited
                else:
                    word = line[:idx_colon]
                    # we expect word in this case to probably be an imap loop
                    imap_loop_id = int(word, 16)
                    if imap_loop_id in self.imapLoops:
                        imap_loop = self.imapLoops[imap_loop_id]

                        # rest should be :server:state(-folder):Function:
                        line = line[idx_colon+1:]
                        idx_colon = line.find(':')
                        server = line[:idx_colon]
                        line = line[idx_colon+1:]
                        idx_colon = line.find(':')
                        state = line[:idx_colon]
                        line = line[idx_colon+1:]
                        idx_colon = line.find(':')
                        func_name = line[:idx_colon]
                        line = line[idx_colon+1:]

                        meth_name = '_imapLoop_func_%s' % (func_name,)
                        meth = getattr(self, meth_name, None)
                        if meth:
                            meth(imap_loop, line)
                        else:
                            print '*** No such function for imapLoop: %s' % (
                                func_name,)
            
            for folder in self.redundantFolders:
                folder.reportRedundancies()

    def _parse_ImapThreadMainLoop(self, line):
        bits = line.split(' ')
        entering = bits[1] == 'entering'
        idx_equals = bits[2].find('=')
        imap_loop_id = int(bits[2][idx_equals+1:-1], 16)
        
        if entering:
            imap_loop = ImapLoop(imap_loop_id)
            self.imapLoops[imap_loop_id] = imap_loop
        else:
            del self.imapLoops[imap_loop_id]

    def _parse_ReadNextLine(self, line):
        pass

    def _parse_queuing(self, line):
        self.track_url_in_str(line)

    def _parse_considering(self, line):
        self.track_url_in_str(line)

    def _parse_creating(self, line):
        self.track_url_in_str(line)

    def _parse_failed(self, line):
        self.track_url_in_str(line)

    def _parse_playing(self, line):
        self.track_url_in_str(line)

    def _parse_retrying(self, line):
        self.track_url_in_str(line)

    # no need to do anything, this is immediately followed by ProcessCurrentURL
    def _imapLoop_func_SetupWithUrl(self, imap_loop, line):
        pass

    def _imapLoop_func_ProcessCurrentURL(self, imap_loop, line):
        if line == ' entering':
            return
        idx_url_end = line.find(':  = currentUrl')
        urlstr = urlparse.unquote(line[:idx_url_end])
        imap_url = self.get_or_create_url(urlstr)

        if imap_url.action == 'fetch':
            folder = self.get_folder_for_imap_url(imap_url)
            if folder.noteDownloads(imap_url, self.iLine, self.thread_id):
                if not folder in self.redundantFolders:
                    self.redundantFolders.append(folder)

            imap_loop.active_fetch_url = imap_url

    def _imapLoop_func_SendData(self, imap_loop, line):
        pass

    FETCH_UID_STR = 'FETCH (UID '
    def _imapLoop_func_CreateNewLineFromSocket(self, imap_loop, line):
        idx_fetch_uid = line.find(self.FETCH_UID_STR)
        idx_body = line.find('BODY[]')
        if idx_fetch_uid != -1 and idx_body != -1:
            #idx_uid_start = idx_fetch_uid += len(self.FETCH_UID_STR)
            #idx_next_space = line.find(' ', idx_uid_start)
            #uid = int(line[idx_uid_start:idx_next_Space])
            imap_loop.active_fetch_url.ref(self.iLine, self.thread_id, line)

    # STREAM:OPEN
    # STREAM:CLOSE
    def _imapLoop_func_STREAM(self, imap_loop, line):
        #print 'STREAM', line
        pass

    def _imapLoop_func_TellThreadToDie(self, imap_loop, line):
        pass

if __name__ == '__main__':
    import sys
    parser = ImapLogParser()
    f = open(sys.argv[1], 'r')
    parser.parse(f)
    f.close()
