# Embedded file name: mud\manifests.pyo
import os
import md5

def getFileHash(ffn):
    fs = os.path.getsize(ffn)
    fi = '%08x' % fs
    f = open(ffn, 'rb')
    bsize = 262144
    while True:
        d = f.read(bsize)
        if not len(d):
            break
        m = md5.new()
        m.update(d)
        fi += m.hexdigest()

    f.close()
    return fi


class builder_listener:

    def tick(self):
        pass

    def progress(self, n):
        pass

    def ignore(self, ffn):
        pass

    def flags(self, ffn):
        return 0


class builder:

    def __init__(self, listener = builder_listener()):
        self.listener = listener

    def count(self, path):
        n = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for name in filenames:
                self.listener.tick()
                ffn = os.path.join(dirpath, name).replace(os.sep, '/')
                if os.path.islink(ffn):
                    continue
                if self.listener.ignore(ffn):
                    continue
                n += 1

        return n

    def walk(self, path, cache = {}):
        n = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for name in filenames:
                self.listener.tick()
                if name[:1] == '.':
                    continue
                ffn = os.path.join(dirpath, name).replace(os.sep, '/')
                pfn = ffn[len(path):]
                if os.path.islink(ffn):
                    continue
                if self.listener.ignore(pfn):
                    continue
                self.listener.progress(n)
                n += 1
                flags = self.listener.flags(pfn)
                fs = os.path.getsize(ffn)
                nfv = (fs, flags)
                print '%d %s' % (flags, pfn)
                if cache.has_key(pfn):
                    fv, fh = cache[pfn]
                    if fv == nfv:
                        continue
                nfh = getFileHash(ffn)
                cache[pfn] = (nfv, nfh)

        return cache