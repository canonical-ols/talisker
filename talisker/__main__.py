import sys
import talisker

talisker.initialise()


def main():
    if len(sys.argv) < 2:
        sys.stderr.write('usage: python -m talisker <python script> ...')

    progname = sys.argv[1]
    with open(progname, 'rb') as fp:
        code = compile(fp.read(), progname, 'exec')
    globs = {
        '__file__': progname,
        '__name__': '__main__',
        '__package__': None,
    }
    sys.argv = sys.argv[1:]
    return exec(code, globs, None)


# When invoked as main program, invoke the profiler on a script
if __name__ == '__main__':
    main()
