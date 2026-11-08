import sys


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    print(" ".join(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
