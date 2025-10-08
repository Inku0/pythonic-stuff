from time import sleep

from utils.webhook_watcher import start_webhook_watcher


def main():
    start_webhook_watcher()
    while True:
        print("Still alive...")
        sleep(300)


if __name__ == "__main__":
    main()
