import sys


def main():
    if not (3, 11) <= sys.version_info[:2] < (3, 13):
        print("Gunakan Python 3.11 atau 3.12 64-bit", file=sys.stderr)
        return 1
    try:
        from app.app import run
    except ImportError as exc:
        print(f"Dependensi belum lengkap: {exc}\n"
              "Jalankan pip install -r requirements.txt",
              file=sys.stderr)
        return 1
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
