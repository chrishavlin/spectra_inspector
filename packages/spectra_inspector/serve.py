from argparse import ArgumentParser

from spectra_inspector.main import app

# Run the App
if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--debug", default=1, help="debug mode on (1) or of (0)")
    ap.add_argument("--host", default=None, help="Host IP")
    ap.add_argument("--port", default=None, help="Port")
    args = ap.parse_args()
    debug = bool(int(args.debug))
    app.run(debug=debug, host=args.host, port=args.port)
