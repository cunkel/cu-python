"""open and close PDF documents in Acrobat Reader on Windows

IF DOCUMENT HAS BEEN CHANGED CHANGES WILL BE SILENTLY DISCARDED.

Can't tell if the document is open, so always prints -1 (not
open) for the page number.

Sometimes must open the docuemnt in order to close it...

As of 2 Apr 2008, requires native Windows Python (not Python for
Cygwin) and pywin32.
"""

import optparse
from os.path import basename, dirname, normcase
import sys

import win32api
import win32con
import win32ui
import dde

__all__ = ["pdfOpen", "pdfClose"]


server = None


def connectToAcrobatDDE():
    global server
    if server is None:
        server = dde.CreateServer()
        server.Create('acroreadctl')
    con = dde.CreateConversation(server)
    try:
        con.ConnectTo('acroview', 'control')
    except dde.error:
        return None
    except Exception:
        return None

    return con


def pdfClose(doc):
    '''Close Acrobat windows with doc open.

    Return None.'''

    pdf = normcase(basename(doc))
    basedir = normcase(dirname(doc))

    acrobat = connectToAcrobatDDE()
    if acrobat is not None:
        try:
            # We must call DocOpen because, until we do, the document is not
            # visible for use by DDE messages.  This has the unfortunate
            # side effect of causing the document to be opened if it is not
            # already.
            acrobat.Exec('[DocOpen("%s")]' % doc)
            acrobat.Exec('[DocClose("%s")]' % doc)
        except Exception:
            raise

    return -1


def pdfOpen(doc, page):
    '''Open an Acrobat window with doc (absolute path) open to page (zero
    indexed).'''

    con = connectToAcrobatDDE()
    if con is None:
        # probably not running
        win32api.ShellExecute(0, 'open', doc, None, dirname(doc),
                              win32con.SW_SHOWNOACTIVATE)
        con = connectToAcrobatDDE()
        if con is None:
            win32api.Sleep(250)
            con = connectToAcrobatDDE()
    else:
        con.Exec('[FileOpen("%s")]' % doc)

    if page > 0 and con is not None:
        try:
            con.Exec('[DocOpen("%s")]' % doc)
            con.Exec('[DocGoTo("%s", %d)]' % (doc, page))
        except dde.error:
            pass


def main():
    parser = optparse.OptionParser(usage="usage: %prog [options] PDFFILE")

    def noAction(pdf, page):
        print("You must specify an action (open, close, or restore.)",
              file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    def closeAction(pdf, page):
        try:
            page = pdfClose(pdf)
        finally:
            if not options.quiet:
                if page is None:
                    print("-1")
                else:
                    print(page)

    def restoreAction(pdf, page):
        if page >= 0:
            pdfOpen(pdf, page)

    parser.set_defaults(todo=noAction, page=-1, quiet=False, debug=False)
    parser.add_option("-c", "--close", action="store_const",
                      dest="todo", const=closeAction,
                      help="close all views of PDFFILE")
    parser.add_option("-o", "--open", action="store_const",
                      dest="todo", const=pdfOpen,
                      help="open view of PDFFILE")
    parser.add_option("-r", "--restore", action="store_const",
                      dest="todo", const=restoreAction,
                      help="restore view of PDFFILE if PAGE is specified"
                      " and nonnegative")
    parser.add_option("-p", "--page", action="store",
                      dest="page", type="int",
                      metavar="PAGE", help="open or restore to PAGE")
    parser.add_option("-q", "--quiet", action="store_true", dest="quiet",
                      help="don't print page PDFFILE was open to")
    parser.add_option("--debug", action="store_true", dest="debug")

    (options, args) = parser.parse_args()

    if len(args) != 1:
        noAction()

    try:
        options.todo(args[0], options.page)
    except Exception:
        if options.debug:
            raise
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
