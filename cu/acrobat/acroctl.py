"""open and close PDF documents in Acrobat Exchange on Windows

The functions do not work with Adobe Reader (i.e. the free PDF viewer)
because it is not an OLE Automation server.  (However, see the
acroreadctl.py script for one that does, with limitations.)

As of 25 Feb 2008, requires native Windows Python (not Python for
Cygwin) and pywin32.
"""

import optparse
from os.path import basename, normcase, abspath
import sys

import win32com.client

__all__ = ["pdfOpen", "pdfClose"]


def pdfClose(doc):
    '''Close Acrobat windows with doc open.

    If PDF file is open, return page number of an (arbitrary) view;
    else None.

    Note: open files are compared only by the filename, NOT including
    the directory.  For example, pdfClose("c:\\some.pdf") would close
    both c:\\spam\\some.pdf and c:\\some.pdf.  It seems that only the
    filename portion is available from the Acrobat OLE interface?'''

    pdf = normcase(basename(doc))

    app = win32com.client.Dispatch("AcroExch.App")
    openTo = None

    avDocs = [app.GetAVDoc(i) for i in range(app.getNumAVDocs())]

    for av in avDocs:
        if normcase(av.GetPDDoc().GetFileName()) == pdf:
            openTo = av.getAVPageView().GetPageNum()
            av.Close(0)  # 0 = ask user to save changes if any

    return openTo


def pdfOpen(doc, page):
    '''Open an Acrobat window with doc open to page (zero indexed).'''

    av = win32com.client.Dispatch("AcroExch.AVDoc")
    av.Open(abspath(doc), None)
    # av.BringToFront()
    av.GetAVPageView().Goto(page)


def main():
    parser = optparse.OptionParser(usage="usage: %prog [options] PDFFILE")

    def noAction(pdf, page):
        sys.stderr.write(
            "You must specify an action (open, close, or restore.)\n")
        parser.print_help()
        sys.exit(1)

    def closeAction(pdf, page):
        page = pdfClose(pdf)
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
        sys.stderr.write("You must specify a filename.")
        parser.print_help()
        sys.exit(1)

    try:
        options.todo(args[0], options.page)
    except Exception:
        if options.debug:
            raise
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
