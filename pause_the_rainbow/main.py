from time import sleep

from utils.rainbow_pause import RBClient


def main():
    RainbowMiner = RBClient()
    RainbowMiner.start_webhook_watcher()
    while True:
        print("Still alive...")
        sleep(300)


if __name__ == "__main__":
    main()
