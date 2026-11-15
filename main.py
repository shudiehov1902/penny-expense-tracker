"""Start Penny locally with: python main.py."""

import os

from tracker import create_app


def main():
    app = create_app()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5050")), debug=False)


if __name__ == "__main__":
    main()
