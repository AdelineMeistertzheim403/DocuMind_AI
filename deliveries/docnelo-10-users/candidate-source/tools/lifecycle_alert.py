"""Optional fixed-content notification hook. Installation is a separate decision."""
from tools.gmail_monitor_alert import send


def main():
    try:
        send({'event':'lifecycle-inventory-failed','reason':'lifecycle-review-required',
              'resource':'planification','severity':'warning'})
    except Exception:
        print('notification_failed')
        return 1
    print('notification_sent')
    return 0


if __name__=='__main__':raise SystemExit(main())
